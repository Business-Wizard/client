#
# -*- coding: utf-8 -*-
"""
config.
"""

import logging

try:
    from collections.abc import Sequence
except ImportError:
    from collections import Sequence

import six
import wandb
from wandb.util import json_friendly

from . import wandb_helper
from .lib import config_util


logger = logging.getLogger("wandb")


# TODO(jhr): consider a callback for persisting changes?
# if this is done right we might make sure this is pickle-able
# we might be able to do this on other objects like Run?
class Config(object):
    """Config object

    Config objects are intended to hold all of the hyperparameters associated with
    a wandb run and are saved with the run object when wandb.init is called.

    We recommend setting wandb.config once at the top of your training experiment or
    setting the config as a parameter to init, ie. wandb.init(config=my_config_dict)

    You can create a file called config-defaults.yaml, and it will automatically be
    loaded into wandb.config. See https://docs.wandb.com/library/config#file-based-configs.

    You can also load a config YAML file with your custom name and pass the filename
    into wandb.init(config="special_config.yaml").
    See https://docs.wandb.com/library/config#file-based-configs.

    Examples:
        Basic usage
        ```
        wandb.config.epochs = 4
        wandb.init()
        for x in range(wandb.config.epochs):
            # train
        ```

        Using wandb.init to set config
        ```
        wandb.init(config={"epochs": 4, "batch_size": 32})
        for x in range(wandb.config.epochs):
            # train
        ```

        Nested configs
        ```
        wandb.config['train']['epochs] = 4
        wandb.init()
        for x in range(wandb.config['train']['epochs']):
            # train
        ```

        Using absl flags

        ```
        flags.DEFINE_string(‘model’, None, ‘model to run’) # name, default, help
        wandb.config.update(flags.FLAGS) # adds all absl flags to config
        ```

        Argparse flags
        ```
        wandb.init()
        wandb.config.epochs = 4

        parser = argparse.ArgumentParser()
        parser.add_argument('-b', '--batch-size', type=int, default=8, metavar='N',
                            help='input batch size for training (default: 8)')
        args = parser.parse_args()
        wandb.config.update(args)
        ```

        Using TensorFlow flags (deprecated in tensorflow v2)
        ```
        flags = tf.app.flags
        flags.DEFINE_string('data_dir', '/tmp/data')
        flags.DEFINE_integer('batch_size', 128, 'Batch size.')
        wandb.config.update(flags.FLAGS)  # adds all of the tensorflow flags to config
        ```
    """

    def __init__(self):
        object.__setattr__(self, "_items", dict())
        object.__setattr__(self, "_locked", dict())
        object.__setattr__(self, "_users", dict())
        object.__setattr__(self, "_users_inv", dict())
        object.__setattr__(self, "_users_cnt", 0)
        object.__setattr__(self, "_callback", None)
        object.__setattr__(self, "_settings", None)

        self._load_defaults()

    def _set_callback(self, cb):
        object.__setattr__(self, "_callback", cb)

    def _set_settings(self, settings):
        object.__setattr__(self, "_settings", settings)

    def __repr__(self):
        return str(dict(self))

    def keys(self):
        return [k for k in self._items.keys() if not k.startswith("_")]

    def _as_dict(self):
        return self._items

    def as_dict(self):
        # TODO: add telemetry, deprecate, then remove
        return dict(self)

    def __getitem__(self, key):
        return self._items[key]

    def __setitem__(self, key, val):
        key, val = self._sanitize(key, val)
        if key in self._locked:
            wandb.termwarn("Config item '%s' was locked." % key)
            return
        self._items[key] = val
        logger.info("config set %s = %s - %s", key, val, self._callback)
        if self._callback:
            self._callback(key=key, val=val, data=self._as_dict())

    def items(self):
        return [(k, v) for k, v in self._items.items() if not k.startswith("_")]

    __setattr__ = __setitem__

    def __getattr__(self, key):
        return self.__getitem__(key)

    def __contains__(self, key):
        return key in self._items

    def _update(self, d, allow_val_change=None):
        parsed_dict = wandb_helper.parse_config(d)
        sanitized = self._sanitize_dict(parsed_dict, allow_val_change)
        self._items.update(sanitized)

    def update(self, d, allow_val_change=None):
        self._update(d, allow_val_change)
        if self._callback:
            self._callback(data=self._as_dict())

    def get(self, *args):
        return self._items.get(*args)

    def persist(self):
        """Calls the callback if it's set"""
        if self._callback:
            self._callback(data=self._as_dict())

    def setdefaults(self, d):
        d = wandb_helper.parse_config(d)
        d = self._sanitize_dict(d)
        for k, v in six.iteritems(d):
            self._items.setdefault(k, v)
        if self._callback:
            self._callback(data=self._as_dict())

    def update_locked(self, d, user=None):
        if user not in self._users:
            # TODO(jhr): use __setattr__ madness
            self._users[user] = self._users_cnt
            self._users_inv[self._users_cnt] = user
            self._users_cnt += 1

        num = self._users[user]

        for k, v in six.iteritems(d):
            k, v = self._sanitize(k, v)
            self._locked[k] = num
            self._items[k] = v

    def _load_defaults(self):
        conf_dict = config_util.dict_from_config_file("config-defaults.yaml")
        if conf_dict is not None:
            self.update(conf_dict)

    def _sanitize_dict(self, config_dict, allow_val_change=None):
        sanitized = {}
        for k, v in six.iteritems(config_dict):
            k, v = self._sanitize(k, v, allow_val_change)
            sanitized[k] = v

        return sanitized

    def _sanitize(self, key, val, allow_val_change=None):
        # Let jupyter change config freely by default
        if self._settings and self._settings._jupyter and allow_val_change is None:
            allow_val_change = True
        # We always normalize keys by stripping '-'
        key = key.strip("-")
        val = self._sanitize_val(val)
        if not allow_val_change and key in self._items and val != self._items[key]:
            raise config_util.ConfigError(
                (
                    'Attempted to change value of key "{}" '
                    "from {} to {}\n"
                    "If you really want to do this, pass"
                    " allow_val_change=True to config.update()"
                ).format(key, self._items[key], val)
            )
        return key, val

    def _sanitize_val(self, val):
        """Turn all non-builtin values into something safe for YAML"""
        if isinstance(val, dict):
            converted = {
                key: self._sanitize_val(value) for key, value in six.iteritems(val)
            }

            return converted
        if isinstance(val, slice):
            converted = dict(
                slice_start=val.start, slice_step=val.step, slice_stop=val.stop
            )
            return converted
        val, _ = json_friendly(val)
        if isinstance(val, Sequence) and not isinstance(val, six.string_types):
            converted = [self._sanitize_val(value) for value in val]
            return converted
        else:
            if val.__class__.__module__ not in ("builtins", "__builtin__"):
                val = str(val)
            return val


class ConfigStatic(object):
    def __init__(self, config):
        object.__setattr__(self, "__dict__", dict(config))

    def __setattr__(self, name, value):
        raise AttributeError("Error: wandb.run.config_static is a readonly object")

    def __setitem__(self, key, val):
        raise AttributeError("Error: wandb.run.config_static is a readonly object")

    def keys(self):
        return self.__dict__.keys()

    def __getitem__(self, key):
        return self.__dict__[key]

    def __str__(self):
        return str(self.__dict__)
