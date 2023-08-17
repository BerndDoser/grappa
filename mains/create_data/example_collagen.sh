# create the spice dataset with amber99sbildn assuming grappa.constants.SPICEPATH and grappa.constants.DEFAULTBASEPATH are set correctly:
# the first two commands must only be run once
set -e
python collagen.py # create unparametrised PDBDataset
python make_graphs.py --ds_name collagen/base -o --collagen --max_energy 65 --max_force 200