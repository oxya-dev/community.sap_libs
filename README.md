# community.sap_libs Ansible Collection

[![CI](https://github.com/sap-linuxlab/community.sap_libs/workflows/CI/badge.svg)](https://github.com/sap-linuxlab/community.sap_libs/actions)[![Codecov](https://img.shields.io/codecov/c/github/sap-linuxlab/community.sap_libs)](https://codecov.io/gh/sap-linuxlab/community.sap_libs)

## Description
This Ansible Collection provides a set of Ansible Modules designed to automate various low-level activities on SAP systems.<br>

It was originally migrated from repository `ansible-collections/community.sap`.

## Requirements

| Component | Control Node | Managed Node |
| :--- | :--- | :--- |
| Operating System | Any OS | [See compatible OS versions](#compatible-operating-system-versions) |
| Python | 3.11 or higher | 3.9 or higher |
| Ansible-Core | 2.18 or higher | N/A |

**Additional notes:**

- **Version Compatibility:** For a detailed mapping of supported Python versions and Ansible-Core lifecycle, refer to the official [Ansible-Core Support Matrix](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html#ansible-core-support-matrix).
- **Control Node Permissions:** Ensure the user executing the playbooks has the necessary SSH keys and sudo privileges configured for the target environment.
- **Managed Node Registration:** Operating system needs to have access to required package repositories either directly or via subscription registration.

### Compatible Operating System Versions

- Red Hat Enterprise Linux for SAP Solutions: 8.x, 9.x, 10.x
- SUSE Linux Enterprise Server for SAP applications: 15 SP5, 15 SP6, 15 SP7, 16

### Important: PyRFC dependency is deprecated

**SAP has discontinued development on `PyRFC` in 2024.**<br>
You can find more details in the [announcement](https://github.com/SAP-archive/PyRFC/issues/372) or in [deprecation notice](https://github.com/SAP-archive/PyRFC?tab=readme-ov-file#deprecation-notice).<br>

The `PyRFC` library is a critical dependency for several modules in this collection, as it is a Python wrapper for the `SAP NW RFC SDK` libraries.<br>
While both `PyRFC` and the `SAP NW RFC SDK` are still available for installation and download at this time, their deprecation means they could be removed without notice.<br>

We will continue to support the modules that depend on `PyRFC` for as long as both the `PyRFC` library and the `SAP NW RFC SDK` remain available.<br>
However, the moment either of them becomes unavailable, we will be forced to cease support for these modules, as they will no longer be functional.<br>

We are investigating potential alternatives, but there is no clear path forward at this time. Users should be aware of this risk when using the affected modules.<br>

Python Library `pyrfc >= 2.4.0` is required for modules:

- `sap_company`
- `sap_snote`
- `sap_task_list_execute`
- `sap_user`
- `sap_pyrfc`


## Installation Instructions

### Installation
Install this collection with Ansible Galaxy command:
```console
ansible-galaxy collection install community.sap_libs
```

### Upgrade
Installed Ansible Collection will not be upgraded automatically when Ansible package is upgraded.

To upgrade the collection to the latest available version, run the following command:
```console
ansible-galaxy collection install community.sap_libs --upgrade
```

You can also install a specific version of the collection, when you encounter issues with latest version. Please report these issues in affected Role repository if that happens.<br>
Example of downgrading collection to version 1.4.0:
```
ansible-galaxy collection install community.sap_libs:==1.4.0
```

See [Installing collections](https://docs.ansible.com/ansible/latest/collections_guide/collections_installing.html) for more details on installation methods.

## Ansible Modules
The following Ansible Modules are included in this collection.

- [sap_hdbsql](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_hdbsql_module.html)
- [sap_task_list_execute](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_task_list_execute_module.html)
- [sapcar_extract](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sapcar_extract_module.html)
- [sap_company](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_company_module.html)
- [sap_snote](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_snote_module.html)
- [sap_user](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_user_module.html)
- [sap_system_facts](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_system_facts_module.html)
- [sap_control_exec](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_control_exec_module.html)
- [sap_pyrfc](https://docs.ansible.com/ansible/latest/collections/community/sap_libs/sap_pyrfc_module.html)

## Testing
This Ansible Collection was tested across different versions of Ansible and Python.<br>
The automated [CI](https://github.com/sap-linuxlab/community.sap_libs/blob/main/.github/workflows/ansible-test.yml) workflow is executing Sanity and Unit tests on following versions.

- `2.18` with Python `3.11 - 3.13`
- `2.19` with Python `3.11 - 3.13`
- `2.20` with Python `3.12 - 3.14`
- `2.21` with Python `3.12 - 3.14`
- `devel` with Python `3.12 - 3.14`

> **NOTE: Compatibility with Python 2 has been dropped in release `1.5.0`.**<br>

### Integration Tests
Due to SAP licensing and hardware requirements, integration tests are momentarily not feasible.<br>
The modules are tested manually against SAP systems until we found a solution or have some modules where we are able to execute integration test we decided to disable these tests.

## Maintainers
You can find more information about maintainers of this Ansible Collection at [MAINTAINERS.md](https://github.com/sap-linuxlab/community.sap_libs/blob/main/MAINTAINERS.md).

## Contributing
We welcome contributions to this collection. For a list of all contributors and information on how you can get involved, please see our [CONTRIBUTORS document](./CONTRIBUTORS.md).

## Support
You can report any issues using [Issues](https://github.com/sap-linuxlab/community.sap_libs/issues) section.

## Release Notes and Roadmap
The release notes for this collection can be found in the [CHANGELOG file](https://github.com/sap-linuxlab/community.sap_libs/blob/main/CHANGELOG.rst).


## Further Information

### Additional sources
You can find more information at following sources:
- [Ansible User guide](https://docs.ansible.com/ansible/devel/user_guide/index.html)
- [Ansible Developer guide](https://docs.ansible.com/ansible/devel/dev_guide/index.html)
- [Ansible Community Code of Conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html)
- [News for Maintainers](https://github.com/ansible-collections/news-for-maintainers)

## License
[Apache 2.0](https://github.com/sap-linuxlab/community.sap_libs/blob/main/LICENSE)
