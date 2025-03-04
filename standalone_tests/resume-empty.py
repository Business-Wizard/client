#!/usr/bin/env python
import random
import wandb

# Run this like:
# WANDB_RUN_ID=xxx WANDB_RESUME=allow python resume-empty.py

run = wandb.init()
print('config', wandb.config)
print('resumed', run.resumed)
config_len = len(wandb.config.keys())
conf_update = {str(config_len): random.random()}
wandb.config.update(conf_update)
