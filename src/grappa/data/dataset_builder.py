from dataclasses import dataclass, field
from typing import Union
from pathlib import Path
import numpy as np
from tqdm import tqdm

from ase.io import read
from ase import Atoms
from ase.calculators.calculator import PropertyNotImplementedError
from ase.geometry.analysis import Analysis

from grappa.data.parameters import Parameters
from grappa.data.molecule import Molecule
from grappa.data.mol_data import MolData
from grappa.utils.openmm_utils import get_nonbonded_contribution
from grappa.utils.system_utils import openmm_system_from_gmx_top, openmm_system_from_dict
from grappa.utils.graph_utils import get_isomorphic_permutation, get_isomorphisms

def get_bonds(geometry: Atoms):
        ana = Analysis(geometry)
        [bonds_raw] = ana.unique_bonds 
        bonds = [[i,n]  for i,nl in  enumerate(bonds_raw) for n in nl]
        return bonds

def match_molecules(molecules: list[Molecule], verbose = False) -> dict[int,list[int]]:
    """Match relative to first Molecule in molecules
    """

    permutations = {0: list(range(len(molecules[0].atoms)))}
    if len(molecules) == 1:
        return permutations

    graphs = [mol.to_dgl() for mol in molecules]

    isomorphisms = get_isomorphisms([graphs[0]],graphs,silent=True)
    matched_idxs = [idxs[1] for idxs in list(isomorphisms)]
    if len(matched_idxs) < len(molecules):
        print(f"Couldn't match all graphs to first graph, only {matched_idxs}!")
        # except RuntimeError as e:
        #     print('Skipping Molecule matching!')
        #     raise e
    if verbose:
        print(isomorphisms)

    for isomorphism in list(isomorphisms):
        [idx1,idx2] = isomorphism
        permutation = get_isomorphic_permutation(graphs[idx1],graphs[idx2])
        permutations[idx2] = permutation
    if verbose:
        print(permutations)
    return permutations

#%%

@dataclass
class DatasetBuilder:
    entries: dict[str,MolData] = field(default_factory=dict)
    complete_entries: set[str] = field(default_factory=set)

    @classmethod
    def from_QM(cls, qm_data_dir: Path, verbose:bool = False):
        """ Expects nested QM data dir. One molecule per directory."""
        entries = {}
        subdirs =  list(qm_data_dir.iterdir())
        for subdir in sorted(subdirs):
            mol_id = subdir.name 
            print(mol_id)
            conformations = []
            gaussian_files = list(subdir.glob(f"*.log")) + list(subdir.glob('*.out'))

            # create geometries: list[list[Atoms]]
            for file in gaussian_files:
                conformations.append(read(file,index=':'))
            
            # different QM files could have different atom order, matching this
            molecules = []
            for conformation_list in conformations:
                molecules.append(Molecule.from_ase(conformation_list[-1]))  #taking [-1] could be better than [0] for optimizations
            permutations = match_molecules(molecules,verbose=verbose)

            # merge conformations
            QM_data = {'xyz':[],'energy':[],'gradient':[]}
            for idx, permutation in permutations.items():
                xyz = []
                energy = []
                gradient = []
                for conformation in conformations[idx]:
                    try:
                        xyz_conf = conformation.get_positions()[[permutation]]
                        energy_conf = conformation.get_potential_energy()
                        force_conf = conformation.get_forces()[permutation]
                        # append after to only add to list if all three properties exist
                        xyz.append(xyz_conf)
                        energy.append(energy_conf)
                        gradient.append(-force_conf)# - to convert from force to gradient
                    except PropertyNotImplementedError as e:
                        print(f"Caught the exception: {e}")
                QM_data['xyz'].extend(np.asarray(xyz))
                QM_data['energy'].extend(np.asarray(energy))
                QM_data['gradient'].extend(np.asarray(gradient)) 

            if len(QM_data['energy']) == 0:
                print(f"No QM data available for {mol_id}")
                continue

            # convert to array
            for k in QM_data.keys():
                QM_data[k] = np.asarray(QM_data[k]).squeeze()

            # create MolData list
            mol_data = MolData(molecule=molecules[0],xyz=QM_data['xyz'],energy=QM_data['energy'],gradient=QM_data['gradient'],mol_id=mol_id)
            entries[mol_id] = mol_data

        return cls(entries=entries)

    def add_nonbonded_from_gmx_top(self, top_data_dir: Path):
        """Replaces molecule of entry with gmx top molecule and permutates moldata xyz and forces
        """
        subdirs =  list(top_data_dir.iterdir())
        for subdir in sorted(subdirs):
            mol_id = subdir.name 
            print(mol_id)     
            if not mol_id in self.entries.keys():   
                print(f"Entry {mol_id} not in DatasetBuilder entries. Skipping!")
                continue
            # get top file
            try:
                top_file = sorted(list(subdir.glob(f"*.top")))[0]
            except IndexError as e:
                print(f"No GROMACS topology file in {subdir}. Skipping!")
                continue

            print(f"Parsing first found topology file: {top_file}.")
            system, topology = openmm_system_from_gmx_top(top_file)
            # create molecule and get permutation
            mol = Molecule.from_openmm_system(system,topology)
            permutations = match_molecules([self.entries[mol_id].molecule,mol])
            if len(permutations) != 2:
                print(f"Couldn't match QM-derived Molecule to gmx top Molecule for {mol_id}.Skipping!")
                continue
            # replace data
            permutation = permutations[1]
            self.entries[mol_id].molecule = mol
            self.entries[mol_id].xyz = self.entries[mol_id].xyz[:,permutation]
            self.entries[mol_id].gradient = self.entries[mol_id].gradient[:,permutation]
            # add nonbonded energy
            # energy, force = get_nonbonded_contribution(system,self.entries[mol_id].xyz)
            self.entries[mol_id].add_ff_data(system,xyz=self.entries[mol_id].xyz)
            self.entries[mol_id]._validate()
            self.complete_entries.add(mol_id)
    
    def remove_bonded_parameters(self):
        """Remove bonded parameters in MolData.classical_parameters and removes bonded energy/force contributions in MolData.ff_energy/force
        """
        for mol_id,moldata in self.entries.items():
            nan_prms = Parameters.get_nan_params(moldata.molecule)
            moldata.classical_parameter_dict = {'reference_ff': nan_prms}
            for contribution in ['bond','angle','proper','improper']:
                for ff_name, ff_dict in moldata.ff_energy.items():
                    ff_dict.pop(contribution,None)
                for ff_name, ff_dict in moldata.ff_gradient.items():
                    ff_dict.pop(contribution,None)

    def write_to_dir(self, dataset_dir: Union[str,Path], overwrite:bool=False):
        """ """
        dataset_dir = Path(dataset_dir)
        dataset_dir.mkdir(parents=True,exist_ok=True)
        npzs_existing = list(dataset_dir.glob('*npz'))
        if len(npzs_existing) > 0:
            print(f"{len(npzs_existing)} npz files already in output directory!")
            if not overwrite:
                print(f"Not writing dataset because npz files are already in directory!")
                return
        mol_ids = self.entries.keys()
        output_entries = []
        for entry_idx in self.complete_entries:
            if entry_idx in mol_ids:
                output_entries.append(entry_idx)
        print(f"Writing {len(output_entries)} complete entries out of {len(self.entries)} total entries in the DatasetBuilder.")
        for output_entry_idx in output_entries:
            self.entries[output_entry_idx].save(dataset_dir / f"{output_entry_idx}.npz")


    def _validate(self):
        """ """
        pass


# %%
