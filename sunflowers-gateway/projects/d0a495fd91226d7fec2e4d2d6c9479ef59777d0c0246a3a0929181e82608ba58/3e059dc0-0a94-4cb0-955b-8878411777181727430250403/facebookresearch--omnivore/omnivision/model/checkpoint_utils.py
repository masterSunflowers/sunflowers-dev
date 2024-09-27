# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import fnmatch
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

import hydra
import torch
import torch.nn as nn
from iopath.common.file_io import g_pathmgr
from omegaconf import OmegaConf

from .model_wrappers import MIMOHeadWrapper


def _unix_pattern_to_parameter_names(
    constraints: List[str], all_parameter_names: Set[str]
) -> Union[None, Set[str]]:
    