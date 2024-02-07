#%%
# PARSE ESPALOMA REPORT SUMMARY
with open("report_summary.csv", "r") as f:
    data = f.read()

# Parse the data
parsed_data = {}
lines = data.split('\n')
for i in range(len(lines)):
    line_parts = lines[i].split()
    # Check if line has enough parts and contains dataset category
    if len(line_parts) > 1:
        if "(te)" in line_parts[1]:

            dataset = line_parts[0].strip('>').strip('<')

            energy_values = lines[i+2].split()[1].replace('$', '').replace('{', '').replace('}', '').split('_')
            force_values = lines[i+3].split()[1].replace('$', '').replace('{', '').replace('}', '').split('_')
            
            energy_mean = float(energy_values[0])
            energy_lower = float(energy_values[1].split('^')[0])
            energy_upper = float(energy_values[1].split('^')[1])
            force_mean = float(force_values[0])
            force_lower = float(force_values[1].split('^')[0])
            force_upper = float(force_values[1].split('^')[1])

            
            # Assuming std is approximated by the difference between the mean and lower bound (or upper bound)
            energy_std = (energy_upper - energy_lower) / 2
            force_std = (force_upper - force_lower) / 2
            
            parsed_data[dataset] = {
                'rmse_energies': {'mean': energy_mean, 'std': energy_std},
                'crmse_gradients': {'mean': force_mean, 'std': force_std}
            }


# Save the data
import json
import numpy as np

with open("espaloma_test_results.json", "w") as f:
    json.dump(parsed_data, f, indent=4)

espaloma_results = parsed_data

print(json.dumps(espaloma_results, indent=4))

import numpy as np
    
with open("results.json", "r") as f:
    grappa_results = json.load(f)


#%%
# sort: small_mol - peptide - rna

boltzmann = [
    'spice-pubchem',
    'spice-des-monomers',
    'spice-dipeptide',
    'spice-dipeptide_amber99sbildn',
    'rna-diverse',
    'rna-trinucleotide',
    'tripeptides_amber99sbildn',
    'dipeptide_rad',
]

opts = [
    'gen2',
    'pepconf-dlc',
    'pepconf-dlc_amber99sbildn',
]

scans = [
    'gen2-torsion',
    'protein-torsion',
    'protein-torsion_amber99sbildn',
]

with open("ds_size.json", "r") as f:
    ds_size = json.load(f)


# now make a large dictionary in the order above:
for ds_order, name in [(boltzmann, 'boltzmann'), (opts, 'opts'), (scans, 'scans')]:
    table = [
        [
            ds, 
            grappa_results['test'][ds]['n_mols'],
            grappa_results['test'][ds]['n_confs'],
            {
                ff: [
                    results['rmse_energies']['mean'],
                    results['rmse_energies']['std'],
                    results['crmse_gradients']['mean'],
                    results['crmse_gradients']['std']
                ] if not results is None else [np.nan, np.nan, np.nan, np.nan]
                for ff, results in [
                    ('Grappa', grappa_results['test'][ds]['grappa']),
                    ('Espaloma', espaloma_results[ds] if ds in espaloma_results.keys() else None),
                    ('Gaff-2.11', grappa_results['test'][ds]['gaff-2.11'] if 'gaff-2.11' in grappa_results['test'][ds].keys() and not 'amber99' in ds else None),
                    ('RNA.OL3', grappa_results['test'][ds]['amber14'] if ds in ['rna-diverse', 'rna-trinucleotide'] else None),
                    ('ff14SB', grappa_results['test'][ds]['amber14'] if 'amber14' in grappa_results['test'][ds].keys() else None),
                ]
            }
        ] for ds in ds_order
    ]

    with open(f"table_{name}.json", "w") as f:
        json.dump(table, f, indent=4)
    
with open("readme.txt", 'w') as f:
    f.write('The json files store lists for every dataset:\n[dsname, n_mols, n_confs, "forcefield": [rmse_energies-mean, rmse_energies-std, crmse_gradients-mean, crmse_gradients-mean]]\nUnits are kcal/mol and Angstrom. crmse is the componentwise-rmse, which is smaller by a factor of sqrt(3) than the actual force-vector rmse.')
# %%

