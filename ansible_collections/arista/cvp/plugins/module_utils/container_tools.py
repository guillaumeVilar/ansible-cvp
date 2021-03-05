#!/usr/bin/env python
# coding: utf-8 -*-
#
# GNU General Public License v3.0+
#
# Copyright 2019 Arista Networks AS-EMEA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
import traceback
import logging
from typing import List
from ansible.module_utils.basic import AnsibleModule
import ansible_collections.arista.cvp.plugins.module_utils.logger   # noqa # pylint: disable=unused-import
from ansible_collections.arista.cvp.plugins.module_utils.response import CvApiResult
try:
    from cvprac.cvp_client import CvpClient
    from cvprac.cvp_client_errors import CvpApiError, CvpRequestError  # noqa # pylint: disable=unused-import
    HAS_CVPRAC = True
except ImportError:
    HAS_CVPRAC = False
    CVPRAC_IMP_ERR = traceback.format_exc()


MODULE_LOGGER = logging.getLogger('arista.cvp.container_tools_v3')
MODULE_LOGGER.info('Start cv_container_v3 module execution')


# CONSTANTS for fields in API data
FIELD_COUNT_DEVICES = 'childNetElementCount'
FIELD_COUNT_CONTAINERS = 'childContainerCount'
FIELD_PARENT_ID = 'parentContainerId'
FIELD_NAME = 'name'
FIELD_KEY = 'key'
FIELD_TOPOLOGY = 'topology'


class CvContainerTools(object):
    """
    CvContainerTools Class to manage container actions for arista.cvp.cv_container module

    [extended_summary]
    """

    def __init__(self, cv_connection: CvpClient, ansible_module: AnsibleModule):
        self._cvp_client = cv_connection
        self._ansible = ansible_module

    #############################################
    ### Private functions
    #############################################

    def _standard_output(self, source: dict):
        """
        _standard_output Filter dict to create a standard output with relevant leys

        Parameters
        ----------
        source : dict
            Original dictionary

        Returns
        -------
        dict
            Standard dict.
        """
        standard_keys = [FIELD_KEY, FIELD_NAME, FIELD_COUNT_CONTAINERS,
                         FIELD_COUNT_DEVICES, FIELD_PARENT_ID]
        return {k: v for k, v in source.items() if k in standard_keys}

    def _get_attached_configlets(self, container_name: str):
        """
        _get_attached_configlets Extract configlet information for all attached configlets to a container

        Example
        -------

        >>> CvContainerTools._get_attached_configlets(container_name='demo')
        [
            {
                'name': 'test',
                'key': 'container-23243-23234-3423423'
            }
        ]

        Parameters
        ----------
        container_name : str
            Name of the container

        Returns
        -------
        list
            List of dict {key:, name:} of attached configlets
        """
        list_configlet = list()
        info = self._cvp_client.api.get_configlets_by_container_id(
            c_id=container_name)
        info = {k.lower(): v for k, v in info.items()}
        for attached_configlet in info['configletList']:
            list_configlet.append(
                self._standard_output(source=attached_configlet))
        return list_configlet

    def _get_all_configlets(self):
        """
        _get_all_configlets Extract information for all configlets

        Example
        -------
        >>> CvContainerTools._get_all_configlets()
        [
            {
                'name': 'test',
                'key': 'container-23243-23234-3423423'
            }
        ]

        Returns
        -------
        list
            List of dict {key:, name:} of attached configlets
        """
        result = list()
        list_configlets = self._cvp_client.api.get_configlets()
        list_configlets = {k.lower(): v for k, v in list_configlets.items()}
        for configlet in list_configlets['data']:
            result.append(self._standard_output(source=configlet))
        return result

    def _get_configlet_info(self, configlet_name: str):
        """
        _get_configlet_info Get information of a configlet from CV

        Example

        >>> CvContainerTools._get_configlet_info(configlet_name='test')
        {
            name: 'test',
            key: 'container-sdsaf'
        }

        Parameters
        ----------
        configlet_name : str
            Name of the configlet to get information

        Returns
        -------
        dict
            Configlet information in a filtered maner
        """
        data = self._cvp_client.api.get_configlet_by_name(name=configlet_name)
        if data is not None:
            return self._standard_output(source=data)
        return None

    def _configlet_add(self, container: dict, configlets: list, save_topology: bool = True):
        """
        _configlet_add Add a list of configlets to a container on CV

        Only execute an API call to attach a list of configlets to a container.
        All configlets must be provided with information and not only name

        Example
        -------

        >>> CvContainerTools._configlet_add(container='test', configlets=[ {key: 'configlet-xxx-xxx-xxx-xxx', name: 'ASE_DEVICE-ALIASES'} ])
        {
            'success': True,
            'taskIDs': [],
            'container': 'DC3',
            'configlets': ['ASE_DEVICE-ALIASES']
        }

        Parameters
        ----------
        container : dict
            Container information to use in API call. Format: {key:'', name:''}
        configlets : list
            List of configlets information to use in API call
        save_topology : bool, optional
            Send a save-topology, by default True

        Returns
        -------
        dict
            API call result
        """
        configlet_names = list()
        container_name = 'Undefined'
        change_response = CvApiResult(action_name=container_name)

        # Protect aginst non-existing container in check_mode
        if container is not None:
            configlet_names = [entry.get('name')
                               for entry in configlets if entry.get('name')]
            change_response.name = container['name']+ ':' + ':'.join(configlet_names)
            if self._ansible.check_mode:
                change_response.success = True
                change_response.taskIds = ['check_mode']
                MODULE_LOGGER.warning(
                    '[check_mode] - Fake container creation of %s', str(container['name']))
            else:
                try:
                    resp = self._cvp_client.api.apply_configlets_to_container(
                        app_name="ansible_cv_container",
                        new_configlets=configlets,
                        container=container,
                        create_task=save_topology
                    )
                except CvpApiError:
                    MODULE_LOGGER.error('Error configuring configlets %s to container %s', str(
                        configlets), str(container))
                else:
                    if 'data' in resp and resp['data']['status'] == 'success':
                        change_response.taskIds = resp['data']['taskIds']
                        change_response.success = True

        return change_response

    def _configlet_del(self, container: dict, configlets: list, save_topology: bool = True):
        """
        _configlet_del Remove a list of configlet from container in CV

        Only execute an API call to reemove a list of configlets from a container.
        All configlets must be provided with information and not only name

        Example
        -------

        >>> CvContainerTools._configlet_del(container='test', configlets=[ {key: 'configlet-xxx-xxx-xxx-xxx', name: 'ASE_DEVICE-ALIASES'} ])
        {
            'success': True,
            'taskIDs': [],
            'container': 'DC3',
            'configlets': ['ASE_DEVICE-ALIASES']
        }

        Parameters
        ----------
        container : dict
            Container information to use in API call. Format: {key:'', name:''}
        configlets : list
            List of configlets information to use in API call
        save_topology : bool, optional
            Send a save-topology, by default True

        Returns
        -------
        dict
            API call result
        """
        configlet_names = list()
        configlet_names = [entry.get('name')
                           for entry in configlets if entry.get('name')]
        change_response = CvApiResult(action_name=container['name'] + ':' + ':'.join(configlet_names))
        if self._ansible.check_mode:
            change_response.success = True
            change_response.taskIds = ['check_mode']
        else:
            try:
                resp = self._cvp_client.api.remove_configlets_from_container(
                    app_name="ansible_cv_container",
                    del_configlets=configlets,
                    container=container,
                    create_task=save_topology
                )
            except CvpApiError:
                MODULE_LOGGER.error('Error removing configlets %s from container %s', str(
                    configlets), str(container))
            else:
                if 'data' in resp and resp['data']['status'] == 'success':
                    change_response.taskIds = resp['data']['taskIds']
                    change_response.success = True

        return change_response

    #############################################
    ### Generic functions
    #############################################

    def get_container_info(self, container_name: str):
        """
        get_container_info Collect container information from CV

        Extract information from Cloudvision using provisioning/filterTopology call

        Example
        -------

        >>> CvContainerTools.get_container_info(container_name='DC2')
        {
            "key": "container_55effafb-2991-45ca-86e5-bf09d4739248",
            "name": "DC1_L3LEAFS",
            "childContainerCount": 5,
            "childNetElementCount": 0,
            "parentContainerId": "container_614c6678-1769-4acf-9cc1-214728238c2f"
        }

        Parameters
        ----------
        container_name : str
            Name of the searched container

        Returns
        -------
        dict
            A standard dictionary with Key, Name, ParentID, Number of children and devices.
        """
        cv_response = self._cvp_client.api.get_container_by_name(
            name=container_name)
        MODULE_LOGGER.debug('Get container ID (%s) response from cv for container %s', str(cv_response), str(container_name))
        if cv_response is not None and FIELD_KEY in cv_response:
            container_id = self._cvp_client.api.get_container_by_name(name=container_name)[
                FIELD_KEY]
            container_facts = self._cvp_client.api.filter_topology(node_id=container_id)[
                FIELD_TOPOLOGY]
            return self._standard_output(source=container_facts)
        return None

    def get_container_id(self, container_name: str):
        """
        get_container_id Collect container ID from CV for a given container

        Example
        >>> CvContainerTools.get_container_id(container_name='DC2')
        container_55effafb-2991-45ca-86e5-bf09d4739248

        Parameters
        ----------
        container_name : str
            Name of the container to get ID

        Returns
        -------
        str
            Container ID sent by CV
        """
        container_info = self._cvp_client.api.get_container_by_name(
            name=container_name)
        if FIELD_KEY in container_info:
            return container_info[FIELD_KEY]
        return None

    #############################################
    ### Boolean & getters functions
    #############################################

    def is_empty(self, container_name: str):
        """
        is_empty Test if container has no child AND no devices attached to it

        Example
        -------
        >>> CvContainerTools.is_empty(container_name='DC2')
        True

        Parameters
        ----------
        container_name : str
            Name of the container to test

        Returns
        -------
        bool
            True if container has no child nor devices
        """
        container = self.get_container_info(container_name=container_name)
        if FIELD_COUNT_CONTAINERS in container and FIELD_COUNT_DEVICES in container:
            if container[FIELD_COUNT_CONTAINERS] == 0 and container[FIELD_COUNT_DEVICES] == 0:
                return True
        return False

    def is_container_exists(self, container_name):
        """
        is_container_exists Test if a given container exists on CV

        Example
        -------
        >>> CvContainerTools.is_container_exists(container_name='DC2')
        True

        Parameters
        ----------
        container_name : [type]
            Name of the container to test

        Returns
        -------
        bool
            True if container exists, False if not
        """
        try:
            cv_data = self._cvp_client.api.get_container_by_name(name=container_name)
        except CvpApiError as error:
            MODULE_LOGGER.error('Error getting information for container %s: %s', str(container_name), str(error))
        if cv_data is not None:
            return True
        return False

    #############################################
    ### Public API
    #############################################

    def create_container(self, container: str, parent: str):
        """
        create_container Worker to send container creation API call to CV

        Example
        -------
        >>> CvContainerTools.create_container(container='DC2', parent='DCs')
        {
            "success": True,
            "taskIDs": [],
            "container": 'DC2'
        }

        Parameters
        ----------
        container : str
            Name of the container to create
        parent : str
            Container name where new container will be created

        Returns
        -------
        dict
            Creation status
        """
        resp = dict()
        change_result = CvApiResult(action_name=container)
        if self.is_container_exists(container_name=parent):
            parent_id = self._cvp_client.api.get_container_by_name(name=parent)[
                FIELD_KEY]
            MODULE_LOGGER.debug('Parent container (%s) for container %s exists', str(parent), str(container))
            if self.is_container_exists(container_name=container) is False:
                if self._ansible.check_mode:
                    change_result.success = True
                    change_result.changed = True
                else:
                    try:
                        resp = self._cvp_client.api.add_container(
                            container_name=container, parent_key=parent_id, parent_name=parent)
                    except CvpApiError:
                        # Add Ansible error management
                        MODULE_LOGGER.error(
                            "Error creating container %s on CV", str(container))
                    else:
                        if resp['data']['status'] == "success":
                            change_result.taskIds = resp['data']['taskIds']
                            change_result.success = True
                            change_result.count += 1
        else:
            MODULE_LOGGER.debug('Parent container (%s) is missing for container %s', str(
                parent), str(container))
        MODULE_LOGGER.info('Container creation result is %s', str(change_result.results))
        return change_result

    def delete_container(self, container: str, parent: str):
        """
        delete_container Worker to send container deletion API call to CV

        Example
        -------
        >>> CvContainerTools.delete_container(container='DC2', parent='DCs')
        {
            "success": True,
            "taskIDs": [],
            "container": 'DC2'
        }

        Parameters
        ----------
        container : str
            Name of the container to delete
        parent : str
            Container name where container will be deleted

        Returns
        -------
        dict
            Deletion status
        """
        resp = dict()
        change_result = CvApiResult(action_name=container)
        if self.is_container_exists(container_name=container) and self.is_empty(container_name=container):
            parent_id = self.get_container_id(container_name=parent)
            container_id = self.get_container_id(container_name=container)
            # ----------------------------------------------------------------#
            # COMMENT: Check mode does report parial change as there is no    #
            # validation that attached containers would be removed in a       #
            # previous run of this function                                   #
            # ----------------------------------------------------------------#
            if self._ansible.check_mode:
                change_result.success = True
            else:
                try:
                    resp = self._cvp_client.api.delete_container(
                        container_name=container, container_key=container_id, parent_key=parent_id, parent_name=parent)
                except CvpApiError:
                    # Add Ansible error management
                    MODULE_LOGGER.error(
                        "Error deleting container %s on CV", str(container))
                else:
                    if resp['data']['status'] == "success":
                        change_result.taskIds = resp['data']['taskIds']
                        change_result.success = True
        else:
            MODULE_LOGGER.debug('Container is missing %s', str(container))
        return change_result

    def configlets_attach(self, container: str, configlets: List[str], strict: bool = False):
        """
        configlets_attach Worker to send configlet attach to container API call

        Example
        -------
        >>> CvContainerTools.configlet_attach(container='DC3', configlets=['ASE_DEVICE-ALIASES'])
        {
            'success': True,
            'taskIDs': [],
            'container': 'DC3',
            'configlets': ['ASE_DEVICE-ALIASES']
        }

        Parameters
        ----------
        container : str
            Name of the container
        configlets : List[str]
            List of configlets to attach
        strict : bool, optional
            Remove configlet not listed in configlets var -- NOT SUPPORTED -- , by default False

        Returns
        -------
        dict
            Action result
        """
        container_info = self.get_container_info(container_name=container)
        attach_configlets = list()
        for configlet in configlets:
            data = self._get_configlet_info(configlet_name=configlet)
            if data is not None:
                attach_configlets.append(data)
        return self._configlet_add(container=container_info, configlets=attach_configlets)

    def configlets_detach(self, container: str, configlets: List[str], strict: bool = False):
        """
        configlets_attach Worker to send configlet detach from container API call

        Example
        -------
        >>> CvContainerTools.configlets_detach(container='DC3', configlets=['ASE_DEVICE-ALIASES'])
        {
            'success': True,
            'taskIDs': [],
            'container': 'DC3',
            'configlets': ['ASE_DEVICE-ALIASES']
        }

        Parameters
        ----------
        container : str
            Name of the container
        configlets : List[str]
            List of configlets to detach
        strict : bool, optional
            Remove configlet not listed in configlets var -- NOT SUPPORTED -- , by default False

        Returns
        -------
        dict
            Action result
        """
        container_info = self.get_container_info(container_name=container)
        detach_configlets = list()
        for configlet in configlets:
            data = self._get_configlet_info(configlet_name=configlet)
            if data is not None:
                detach_configlets.append(data)
        return self._configlet_del(container=container_info, configlets=detach_configlets)


class ContainerInput():
    """
    ContainerInput Object to manage Container Topology in context of arista.cvp collection.

    [extended_summary]
    """
    def __init__(self, user_topology: dict, container_root_name: str = 'Tenant'):
        self._topology = user_topology
        self._parent_field: str = 'parent_container'
        self._root_name = container_root_name

    def _get_container_data(self, container_name: str, key_name: str):
        """
        _get_container_data Get a specific subset of data for a given container

        Parameters
        ----------
        container_name : str
            Name of the container
        key_name : str
            Name of the key to extract

        Returns
        -------
        Any
            Value of the key. None if not found
        """
        MODULE_LOGGER.debug('Receive request to get data for container %s about its %s key', str(container_name), str(key_name))
        if container_name in self._topology:
            if key_name in self._topology[container_name]:
                MODULE_LOGGER.debug('  -> Found data for container %s: %s', str(
                    container_name), str(self._topology[container_name][key_name]))
                return self._topology[container_name][key_name]
        return None

    @property
    def ordered_list_containers(self):
        """
        ordered_list_containers List of container from root to the bottom

        Returns
        -------
        list
            List of containers
        """
        result_list = list()
        MODULE_LOGGER.info(
            "Build list of container to create from %s", str(self._topology))
        while(len(result_list) < len(self._topology)):
            for container in self._topology:
                if self._topology[container][self._parent_field] == self._root_name:
                    result_list.append(container)
                if (any(element == self._topology[container][self._parent_field] for element in result_list)
                        and container not in result_list):
                    result_list.append(container)
        MODULE_LOGGER.info('List of containers to apply on CV: %s', str(result_list))
        return result_list

    def get_parent(self, container_name: str, parent_key: str = 'parent_container'):
        """
        get_parent Expose name of parent container for the given container

        Parameters
        ----------
        container_name : str
            Container Name
        parent_key : str, optional
            Key to use for the parent container name, by default 'parent_container'

        Returns
        -------
        str
            Name of the parent container, None if not found
        """
        return self._get_container_data(container_name=container_name, key_name=parent_key)

    def get_configlets(self, container_name: str, configlet_key: str = 'configlets'):
        return self._get_container_data(container_name=container_name, key_name=configlet_key)

    def has_configlets(self, container_name, configlet_key: str = 'configlets'):
        if self._get_container_data(container_name=container_name, key_name=configlet_key) is None:
            return False
        return True