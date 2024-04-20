"""
Training a model on the spice-dipeptides dataset.
"""
#%%
from grappa.training.trainrun import do_trainrun
import yaml

# load the config:
with open("grappa_config.yaml", "r") as f:
    config = yaml.safe_load(f)

# reduce the datasets to only the dipeptide dataset:
config["data_config"]["datasets"] = ["spice-dipeptide"]
config["data_config"]["pure_train_datasets"] = []
config["data_config"]["pure_test_datasets"] = []

#%%
do_trainrun(config=config, project="grappa_example")