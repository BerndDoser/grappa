# NOTE: use dataset class!

from grappa.data import MolData
from pathlib import Path
import numpy as np

def main(source_path, target_path, forcefield='openff_unconstrained-2.0.0.offxml'):
    print(f"Converting\n{source_path}\nto\n{target_path}")
    source_path = Path(source_path)
    target_path = Path(target_path)

    target_path.mkdir(exist_ok=True, parents=True)

    # iterate over all child directories of source_path:
    num_total = 0
    num_success = 0
    num_err = 0

    total_mols = 0
    total_confs = 0

    for idx, molfile in enumerate(source_path.iterdir()):
        if molfile.is_dir():
            continue
        num_total += 1
        try:
            print(f"Processing {idx}", end='\r')
            data = np.load(molfile)
            # ransform to actual dictionary
            data = {k:v for k,v in data.items()}

            moldata = MolData.from_data_dict(data_dict=data, partial_charge_key='am1bcc_elf_charges', forcefield=forcefield)

            total_mols += 1
            total_confs += data['xyz'].shape[0]

            moldata.save(target_path/(molfile.stem+'.npz'))

            num_success += 1
        except Exception as e:
            num_err += 1
            raise
            # print(f"Failed to process {molpath}: {e}")
            continue
    
    print("\nDone!")
    print(f"Processed {num_total} molecules, {num_success} successfully, {num_err} with errors")

    print(f"Total mols: {total_mols}, total confs: {total_confs}")

import argparse
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source_path",
        type=str,
        help="Path to the folder with npz files containing smiles, positions, energies and gradients.",
    )
    parser.add_argument(
        "--target_path",
        type=str,
        help="Path to the target folder in which the dataset is stored as collection of npz files.",
    )
    parser.add_argument(
        "--forcefield",
        type=str,
        default='openff_unconstrained-2.0.0.offxml',
        help="Which forcefield to use for creating improper torsion and classical parameters. if no energy_ref and gradient_ref are given, the nonbonded parameters are used as reference.",
    )
    args = parser.parse_args()
    main(source_path=args.source_path, target_path=args.target_path, forcefield=args.forcefield)