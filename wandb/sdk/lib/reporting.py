"""
reporting.
"""

import logging

logger = logging.getLogger("wandb")


class _Reporter(object):
    def __init__(self, settings):
        self._settings = settings
        self._errors = []
        self._warnings = []
        self._num_errors = 0
        self._num_warnings = 0
        self._context = {}

    def error(self, __s, *args):
        pass

    def warning(self, __s, *args):
        show = self._settings.show_warnings
        summary = self._settings.summary_warnings
        if show is not None or summary is not None:
            s = __s % args
        self._num_warnings += 1
        if show is not None and (self._num_warnings <= show or show == 0):
            print("[WARNING]", s)
            if self._num_warnings == show:
                print("not showing any more warnings")
        if summary is not None and (self._num_warnings <= summary or summary == 0):
            self._warnings.append(s)

    def info(self, __s, *args):
        if self._settings.show_info:
            print(f'[INFO]{__s}' % args)

    def internal(self, __s, *args):
        pass

    def problem(self, bool, __s=None, *args):
        pass

    def set_context(self, __d=None, **kwargs):
        if __d:
            self._context.update(__d)
        self._context.update(**kwargs)

    def clear_context(self, keys=None):
        if keys is None:
            self._context = {}
            return
        for k in keys:
            self._context.pop(k, None)

    @property
    def warning_count(self):
        return self._num_warnings

    @property
    def error_count(self):
        return self._num_errors

    @property
    def warning_lines(self):
        return self._warnings

    @property
    def error_lines(self):
        return self._errors


class Reporter(object):
    _instance = None

    def __init__(self, settings=None):
        if Reporter._instance is not None:
            return
        if settings is None:
            logging.error("internal issue: reporter not setup")

        Reporter._instance = _Reporter(settings)

    def __getattr__(self, name):
        return getattr(self._instance, name)


def setup_reporter(settings):
    if not settings.is_frozen():
        logging.error("internal issue: settings not frozen")
    return Reporter(settings=settings)


def get_reporter():
    return Reporter()
