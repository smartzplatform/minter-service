
import os
import yaml


class ConfigurationBase(object):
    """
    Base class for configurations.
    """

    def __init__(self, filename):
        self.filename = filename

        with open(filename) as fh:
            self._conf = yaml.safe_load(fh)


    def __getitem__(self, key):
        return self._conf[key]

    def __contains__(self, item):
        return item in self._conf

    def get(self, key, default):
        return self._conf.get(key, default)


    def _check_existence(self, names):
        for name in names if isinstance(names, (list, tuple)) else (names, ):
            if self._conf.get(name) is None:
                raise ValueError(name + ' is not provided')

    def _check_strings(self, names):
        self._check_existence(names)
        for name in names if isinstance(names, (list, tuple)) else (names, ):
            if not isinstance(name, str):
                raise TypeError('setting {} is not a string'.format(name))

    def _check_ints(self, names):
        self._check_existence(names)
        for name in names if isinstance(names, (list, tuple)) else (names, ):
            try:
                int(self._conf[name])
            except ValueError:
                raise ValueError(name + ' is not an integer')

    def _check_dirs(self, names, writable=False):
        self._check_strings(names)
        for name in names if isinstance(names, (list, tuple)) else (names, ):
            dir_path = str(self._conf[name])
            if not os.path.isdir(dir_path):
                raise ValueError('setting {}: {} is not a directory'.format(name, dir_path))
            if not os.access(dir_path, os.R_OK | os.X_OK):
                raise ValueError('setting {}: directory {} is not readable'.format(name, dir_path))
            if writable and not os.access(dir_path, os.W_OK):
                raise ValueError('setting {}: directory {} is not writable'.format(name, dir_path))
