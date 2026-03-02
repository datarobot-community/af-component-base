# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import hashlib
import logging
import os
from typing import Any, Iterable, cast

import datarobot as dr
from datarobot._experimental.fs.file_system import DataRobotFileSystem

from core.persistent_fs.kv_custom_app_implementattion import (
    KeyValue,
    KeyValueEntityType,
)


logger = logging.getLogger(__name__)


CATALOG_STORAGE_NAME = "fs_catalog"
FILE_API_CONNECT_TIMEOUT = float(os.environ.get("FILE_API_CONNECT_TIMEOUT", 180))
FILE_API_READ_TIMEOUT = float(os.environ.get("FILE_API_READ_TIMEOUT", 180))


class DRFileSystem(DataRobotFileSystem):
    """
    DRFileSystem is fsspec implementation for interact with Datarobot
    KeyValue and File storage for having persistent storage inside
    custom applications.
    """
    _catalog_id: str | None = None

    def __init__(
        self,
        dr_client: dr.rest.RESTClientObject | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.client = dr_client or dr.Client(
            token=os.environ.get("DATAROBOT_API_TOKEN"),
            endpoint=os.environ.get("DATAROBOT_ENDPOINT"),
        )
        self.app_id: str = os.environ.get("APPLICATION_ID")  # type: ignore[assignment]
        if not self.app_id:
            raise ValueError("APPLICATION_ID env variable is not set.")
        self._catalog_id = None
        self._initialize_catalog_id()

    def _initialize_catalog_id(self) -> None:
        with self.client:
            catalog_stored = KeyValue.find(
                self.app_id,
                KeyValueEntityType.CUSTOM_APPLICATION,
                CATALOG_STORAGE_NAME,
            )
            if catalog_stored:
                self._catalog_id = catalog_stored.value
            else:
                self._catalog_id = self.create_catalog_item_dir()
                KeyValue.create(
                    entity_id=self.app_id,
                    entity_type=KeyValueEntityType.CUSTOM_APPLICATION,
                    name=CATALOG_STORAGE_NAME,
                    category=dr.KeyValueCategory.ARTIFACT,
                    value_type=dr.KeyValueType.STRING,
                    value=self._catalog_id,
                )
    
    def _split_path(self, path: str):
        path_without_protocol = self._strip_protocol(path)
        if not path_without_protocol:
            raise ValueError(
                f"Invalid path '{path}'. Expected format: '{self.protocol}://path/to/file.txt'"
            )
        return self._catalog_id, path_without_protocol
    
    def mkdir(self, *args: Iterable[Any], **kwargs: Any) -> None:
        pass

    def makedirs(self, *args: Iterable[Any], **kwargs: Any) -> None:
        pass


def calculate_checksum(path: str) -> bytes:
    adder = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(8192):
            adder.update(chunk)
    return adder.digest()

def all_env_variables_present() -> bool:
    # check if all env variables are present
    expected_envs = ["DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN", "APPLICATION_ID"]
    return not any(not os.environ.get(env_name) for env_name in expected_envs)