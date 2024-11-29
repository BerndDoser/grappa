from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from tqdm import tqdm

from ase.io import read
from ase import Atoms
from ase.calculators.calculator import PropertyNotImplementedError
from ase.geometry.analysis import Analysis


from grappa.data.molecule import Molecule
from grappa.data.mol_data import MolData
from grappa.utils.data_utils import get_moldata_path
from grappa.utils.graph_utils import get_isomorphisms

from grappa.utils.graph_utils import get_isomorphic_permutation

TQDM_DISABLE=1

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

    isomorphisms = []
    for i,graph in enumerate(graphs[1:]):
        try:
            isomorphism = get_isomorphisms([graphs[0]],[graph],silent=True)
            if len(isomorphism) == 1 :
                isomorphisms.append(isomorphism)
            else:
                print(f"Couldn't match graph {i} to first graph in molecules!")
        except RuntimeError as e:
            print('Skipping Molecule matching!')
            raise e
    if verbose:
        print(isomorphisms)

    for isomorphism in isomorphisms:
        [idx1,idx2] = list(isomorphism)[0]
        permutation = get_isomorphic_permutation(graphs[idx1],graphs[idx2])
        if verbose:
            print(permutation)
        permutations[idx2] = permutation
    return permutations

#%%

@dataclass
class DatasetBuilder:
    entries: dict[str,MolData] = field(default_factory=dict)

    @classmethod
    def from_QM(cls, qm_data_dir: Path):
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
            permutations = match_molecules(molecules,verbose=False)

            if len(permutations) == 0:
                continue

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

    def write_to_dir(self, directory: str):
        """ """
        pass

    def match_gmx_top(self, topology):
        """ """
        pass

    def _validate(self):
        """ """
        pass


# %%
