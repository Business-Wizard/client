# -*- coding: utf-8 -*-
"""Backend - Send to internal process

Manage backend.

"""

import logging
import os
import sys

import wandb

from ..interface import interface
from ..internal.internal import wandb_internal

logger = logging.getLogger("wandb")


class Backend(object):
    def __init__(self):
        self._done = False
        self.record_q = None
        self.result_q = None
        self.wandb_process = None
        self.interface = None
        self._internal_pid = None
        self._wl = wandb.setup()

    def _hack_set_run(self, run):
        self.interface._hack_set_run(run)

    def ensure_launched(
        self,
        settings=None,
        log_level=None,
        stdout_fd=None,
        stderr_fd=None,
        use_redirect=None,
    ):
        """Launch backend worker if not running."""
        settings = dict(settings or ())
        settings["_log_level"] = log_level or logging.DEBUG

        # TODO: this is brittle and should likely be handled directly on the
        # settings object.  Multi-processing blows up when it can't pickle
        # objects.
        if "_early_logger" in settings:
            del settings["_early_logger"]

        self.record_q = self._wl._multiprocessing.Queue()
        self.result_q = self._wl._multiprocessing.Queue()
        self.wandb_process = self._wl._multiprocessing.Process(
            target=wandb_internal,
            kwargs=dict(
                settings=settings, record_q=self.record_q, result_q=self.result_q,
            ),
        )
        self.wandb_process.name = "wandb_internal"

        # Support running code without a: __name__ == "__main__"
        save_mod_name = None
        save_mod_path = None
        main_module = sys.modules["__main__"]
        main_mod_spec = getattr(main_module, "__spec__", None)
        main_mod_path = getattr(main_module, "__file__", None)
        main_mod_name = getattr(main_mod_spec, "name", None) if main_mod_spec else None
        if main_mod_name is not None:
            save_mod_name = main_mod_name
            main_module.__spec__.name = "wandb.mpmain"
        elif main_mod_path is not None:
            save_mod_path = main_module.__file__
            fname = os.path.join(
                os.path.dirname(wandb.__file__), "mpmain", "__main__.py"
            )
            main_module.__file__ = fname

        # Start the process with __name__ == "__main__" workarounds
        self.wandb_process.start()
        self._internal_pid = self.wandb_process.pid

        # Undo temporary changes from: __name__ == "__main__"
        if save_mod_name:
            main_module.__spec__.name = save_mod_name
        elif save_mod_path:
            main_module.__file__ = save_mod_path

        self.interface = interface.BackendSender(
            process=self.wandb_process, record_q=self.record_q, result_q=self.result_q,
        )

    def server_connect(self):
        """Connect to server."""
        pass

    def server_status(self):
        """Report server status."""
        pass

    def cleanup(self):
        # TODO: make _done atomic
        if self._done:
            return
        self._done = True
        self.interface.join()
        self.wandb_process.join()
        self.record_q.close()
        self.result_q.close()
        # No printing allowed from here until redirect restore!!!
