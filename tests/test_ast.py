import shutil

import yaml
from salt_lsp.parser import parse
from salt_lsp.types import (AstNode, ExtendNode, IncludeNode, IncludesNode,
                            Position, RequisiteNode, RequisitesNode,
                            StateCallNode, StateNode, StateParameterNode,
                            TokenNode, Tree)

from tests.utils import doc_to_fileuri


class TestIncludeNode:
    def test_get_file_with_no_value(self):
        assert IncludeNode(value=None).get_file("") is None

    def test_get_file_from_init_sls(self, fs):
        fs.create_file("/repo/root/foo/init.sls")
        assert (
            IncludeNode(value="foo").get_file("/repo/root/top.sls")
            == "/repo/root/foo/init.sls"
        )

    def test_get_file_from_foo_sls(self, fs):
        fs.create_file("/repo/root/foo.sls")
        assert (
            IncludeNode(value="foo").get_file("/repo/root/top.sls")
            == "/repo/root/foo.sls"
        )

    def test_get_file_when_sls_not_present(self):
        assert IncludeNode(value="foo").get_file("/repo/root/top.sls") is None


def test_includes():
    content = """include:
  - foo.bar
  - web
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=2, col=7),
        includes=IncludesNode(
            start=Position(line=0, col=0),
            end=Position(line=2, col=7),
            includes=[
                IncludeNode(
                    start=Position(line=1, col=2),
                    end=Position(line=1, col=11),
                    value="foo.bar",
                ),
                IncludeNode(
                    start=Position(line=2, col=2),
                    end=Position(line=2, col=7),
                    value="web",
                ),
            ],
        ),
    )


def test_simple_state():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: root
    - group: root
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=3, col=17),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=3, col=17),
                identifier="/etc/systemd/system/rootco-salt-backup.service",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=3, col=17),
                        name="file.managed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="user",
                                value="root",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=3, col=17),
                                name="group",
                                value="root",
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def test_extend():
    content = """extend:
  /etc/systemd/system/rootco-salt-backup.service:
    file.managed:
      - user: root
      - group: root
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=4, col=19),
        extend=ExtendNode(
            start=Position(line=0, col=0),
            end=Position(line=4, col=19),
            states=[
                StateNode(
                    start=Position(line=1, col=2),
                    end=Position(line=4, col=19),
                    identifier="/etc/systemd/system/rootco-salt-backup.service",
                    states=[
                        StateCallNode(
                            start=Position(line=2, col=4),
                            end=Position(line=4, col=19),
                            name="file.managed",
                            parameters=[
                                StateParameterNode(
                                    start=Position(line=3, col=6),
                                    end=Position(line=4, col=6),
                                    name="user",
                                    value="root",
                                ),
                                StateParameterNode(
                                    start=Position(line=4, col=6),
                                    end=Position(line=4, col=19),
                                    name="group",
                                    value="root",
                                ),
                            ],
                        )
                    ],
                )
            ],
        ),
    )


def test_requisites():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: root
    - group: root
    - require:
      - file: /foo/bar
      - service: libvirtd
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=6, col=25),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=6, col=25),
                identifier="/etc/systemd/system/rootco-salt-backup.service",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=6, col=25),
                        name="file.managed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="user",
                                value="root",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=4, col=4),
                                name="group",
                                value="root",
                            ),
                        ],
                        requisites=[
                            RequisitesNode(
                                start=Position(line=4, col=4),
                                end=Position(line=6, col=25),
                                kind="require",
                                requisites=[
                                    RequisiteNode(
                                        start=Position(line=5, col=6),
                                        end=Position(line=6, col=6),
                                        module="file",
                                        reference="/foo/bar",
                                    ),
                                    RequisiteNode(
                                        start=Position(line=6, col=6),
                                        end=Position(line=6, col=25),
                                        module="service",
                                        reference="libvirtd",
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )


def create_mark(content, line, col, index):
    return yaml.Mark(
        name="<unicode string>",
        line=line,
        column=col,
        buffer=f"{content}\x00",
        pointer=index,
        index=index,
    )


def test_complex_parameter_state():
    content = """saltmaster.packages:
  pkg.installed:
    - pkgs:
      - salt-master
      - sshd
      - git
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=5, col=11),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=5, col=11),
                identifier="saltmaster.packages",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=5, col=11),
                        name="pkg.installed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=5, col=11),
                                name="pkgs",
                                value=[
                                    TokenNode(
                                        yaml.BlockEntryToken(
                                            start_mark=create_mark(
                                                line=3,
                                                col=6,
                                                content=content,
                                                index=56,
                                            ),
                                            end_mark=create_mark(
                                                line=3,
                                                col=7,
                                                content=content,
                                                index=57,
                                            ),
                                        )
                                    ),
                                    TokenNode(
                                        yaml.ScalarToken(
                                            start_mark=create_mark(
                                                line=3,
                                                col=8,
                                                content=content,
                                                index=58,
                                            ),
                                            end_mark=create_mark(
                                                line=3,
                                                col=19,
                                                content=content,
                                                index=69,
                                            ),
                                            value="salt-master",
                                            plain=True,
                                        )
                                    ),
                                    TokenNode(
                                        yaml.BlockEntryToken(
                                            start_mark=create_mark(
                                                line=4,
                                                col=6,
                                                content=content,
                                                index=76,
                                            ),
                                            end_mark=create_mark(
                                                line=4,
                                                col=7,
                                                content=content,
                                                index=77,
                                            ),
                                        )
                                    ),
                                    TokenNode(
                                        yaml.ScalarToken(
                                            start_mark=create_mark(
                                                line=4,
                                                col=8,
                                                content=content,
                                                index=78,
                                            ),
                                            end_mark=create_mark(
                                                line=4,
                                                col=12,
                                                content=content,
                                                index=82,
                                            ),
                                            value="sshd",
                                            plain=True,
                                        )
                                    ),
                                    TokenNode(
                                        yaml.BlockEntryToken(
                                            start_mark=create_mark(
                                                line=5,
                                                col=6,
                                                content=content,
                                                index=89,
                                            ),
                                            end_mark=create_mark(
                                                line=5,
                                                col=7,
                                                content=content,
                                                index=90,
                                            ),
                                        )
                                    ),
                                    TokenNode(
                                        yaml.ScalarToken(
                                            start_mark=create_mark(
                                                line=5,
                                                col=8,
                                                content=content,
                                                index=91,
                                            ),
                                            end_mark=create_mark(
                                                line=5,
                                                col=11,
                                                content=content,
                                                index=94,
                                            ),
                                            value="git",
                                            plain=True,
                                        )
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def test_duplicate_key():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: root
    - user: bar
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=3, col=15),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=3, col=15),
                identifier="/etc/systemd/system/rootco-salt-backup.service",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=3, col=15),
                        name="file.managed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="user",
                                value="root",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=3, col=15),
                                name="user",
                                value="bar",
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def test_empty_requisite_item():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: root
    - group: root
    - require:
      - file: /foo/bar
      - 

git -C /srv/salt pull -q:
  cron.present:
    - user: root
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=10, col=16),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=8, col=0),
                identifier="/etc/systemd/system/rootco-salt-backup.service",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=8, col=0),
                        name="file.managed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="user",
                                value="root",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=4, col=4),
                                name="group",
                                value="root",
                            ),
                        ],
                        requisites=[
                            RequisitesNode(
                                start=Position(line=4, col=4),
                                end=Position(line=8, col=0),
                                kind="require",
                                requisites=[
                                    RequisiteNode(
                                        start=Position(line=5, col=6),
                                        end=Position(line=6, col=6),
                                        module="file",
                                        reference="/foo/bar",
                                    ),
                                    RequisiteNode(
                                        start=Position(line=6, col=6),
                                        end=Position(line=8, col=0),
                                        module=None,
                                        reference=None,
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            ),
            StateNode(
                start=Position(line=8, col=0),
                end=Position(line=10, col=16),
                identifier="git -C /srv/salt pull -q",
                states=[
                    StateCallNode(
                        start=Position(line=9, col=2),
                        end=Position(line=10, col=16),
                        name="cron.present",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=10, col=4),
                                end=Position(line=10, col=16),
                                name="user",
                                value="root",
                            ),
                        ],
                    )
                ],
            ),
        ],
    )


def test_empty_parameter():
    content = """/srv/git/salt-states:
  file.symlink:
    -
    - target: /srv/salt
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=3, col=23),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=3, col=23),
                identifier="/srv/git/salt-states",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=3, col=23),
                        name="file.symlink",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name=None,
                                value=None,
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=3, col=23),
                                name="target",
                                value="/srv/salt",
                            ),
                        ],
                    )
                ],
            ),
        ],
    )


def test_empty_last_parameter():
    content = """/srv/git/salt-states:
  file.symlink:
    - target: /srv/salt
    -
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=3, col=5),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=3, col=5),
                identifier="/srv/git/salt-states",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=3, col=5),
                        name="file.symlink",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="target",
                                value="/srv/salt",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=3, col=5),
                                name=None,
                                value=None,
                            ),
                        ],
                    )
                ],
            ),
        ],
    )


def test_top_sls():
    content = """base:
  '*':
    - common
    - ca
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=3, col=8),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=3, col=8),
                identifier="base",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=3, col=8),
                        name="*",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="common",
                                value=None,
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=3, col=8),
                                name="ca",
                                value=None,
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def test_state_no_param():
    content = """jdoe:
  user.present
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=1, col=14),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=1, col=14),
                identifier="jdoe",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=1, col=14),
                        name="user.present",
                    )
                ],
            )
        ],
    )


def test_state_unfinished_state_id():
    content = """jdoe
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=0, col=4),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=0, col=4),
                identifier="jdoe",
            )
        ],
    )


def test_scan_error():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: root
    - group: root
  virt

"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=5, col=0),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=5, col=0),
                identifier="/etc/systemd/system/rootco-salt-backup.service",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=4, col=2),
                        name="file.managed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="user",
                                value="root",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=4, col=2),
                                name="group",
                                value="root",
                            ),
                        ],
                    ),
                    StateCallNode(
                        start=Position(line=4, col=2),
                        end=Position(line=5, col=0),
                        name="virt",
                    ),
                ],
            )
        ],
    )


def test_visit():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: root
    - group: root
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    pos = Position(line=2, col=8)
    found_node = None

    def visitor(node: AstNode) -> bool:
        if pos >= node.start and pos < node.end:
            nonlocal found_node
            found_node = node
        return True

    tree.visit(visitor)
    assert found_node == StateParameterNode(
        start=Position(line=2, col=4),
        end=Position(line=3, col=4),
        name="user",
        value="root",
    )


def test_pop_breadcrumb_from_flow_sequence():
    """
    This is a regression test for https://github.com/dcermak/salt-lsp/issues/3
    """
    content = """apache2:
   pkg.installed: []
   service.running:
     - enable: true
     - require:
       - pkg: apache2
   file.managed: {}
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=6, col=19),
        includes=None,
        extend=None,
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=6, col=19),
                identifier="apache2",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=3),
                        end=Position(line=1, col=20),
                        name="pkg.installed",
                        parameters=[],
                        requisites=[],
                    ),
                    StateCallNode(
                        start=Position(line=2, col=3),
                        end=Position(line=6, col=3),
                        name="service.running",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=3, col=5),
                                end=Position(line=4, col=5),
                                name="enable",
                                value="true",
                            )
                        ],
                        requisites=[
                            RequisitesNode(
                                start=Position(line=4, col=5),
                                end=Position(line=6, col=3),
                                kind="require",
                                requisites=[
                                    RequisiteNode(
                                        start=Position(line=5, col=7),
                                        end=Position(line=6, col=3),
                                        module="pkg",
                                        reference="apache2",
                                    )
                                ],
                            )
                        ],
                    ),
                    StateCallNode(
                        start=Position(line=6, col=3),
                        end=Position(line=6, col=19),
                        name="file.managed",
                        parameters=[],
                        requisites=[],
                    ),
                ],
            )
        ],
    )


def test_list_index_out_of_range():
    content = """
root:
  user.present

ilmehtar:
  user.present:
    - fullname: Richard Brown
    - home: /home/ilmehtar
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=7, col=26),
        includes=None,
        extend=None,
        states=[
            StateNode(
                start=Position(line=1, col=0),
                end=Position(line=2, col=14),
                identifier="root",
                states=[
                    StateCallNode(
                        start=Position(line=2, col=2),
                        end=Position(line=2, col=14),
                        name="user.present",
                        parameters=[],
                        requisites=[],
                    )
                ],
            ),
            StateNode(
                start=Position(line=4, col=0),
                end=Position(line=7, col=26),
                identifier="ilmehtar",
                states=[
                    StateCallNode(
                        start=Position(line=5, col=2),
                        end=Position(line=7, col=26),
                        name="user.present",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=6, col=4),
                                end=Position(line=7, col=4),
                                name="fullname",
                                value="Richard Brown",
                            ),
                            StateParameterNode(
                                start=Position(line=7, col=4),
                                end=Position(line=7, col=26),
                                name="home",
                                value="/home/ilmehtar",
                            ),
                        ],
                        requisites=[],
                    )
                ],
            ),
        ],
    )


def test_jinja():
    content = """/etc/systemd/system/rootco-salt-backup.service:
  file.managed:
    - user: {{ pillar.get('user').get('name') }}
    - group: {{ grains.group }}
    - require:
      - file: /foo/bar
      - service: libvirtd
"""
    directory, uri = doc_to_fileuri(content)
    tree = parse(uri, content)
    shutil.rmtree(directory)
    assert tree == Tree(
        start=Position(line=0, col=0),
        end=Position(line=6, col=25),
        states=[
            StateNode(
                start=Position(line=0, col=0),
                end=Position(line=6, col=25),
                identifier="/etc/systemd/system/rootco-salt-backup.service",
                states=[
                    StateCallNode(
                        start=Position(line=1, col=2),
                        end=Position(line=6, col=25),
                        name="file.managed",
                        parameters=[
                            StateParameterNode(
                                start=Position(line=2, col=4),
                                end=Position(line=3, col=4),
                                name="user",
                                value="pillar.get('user').get('name')",
                            ),
                            StateParameterNode(
                                start=Position(line=3, col=4),
                                end=Position(line=4, col=4),
                                name="group",
                                value="grains.group",
                            ),
                        ],
                        requisites=[
                            RequisitesNode(
                                start=Position(line=4, col=4),
                                end=Position(line=6, col=25),
                                kind="require",
                                requisites=[
                                    RequisiteNode(
                                        start=Position(line=5, col=6),
                                        end=Position(line=6, col=6),
                                        module="file",
                                        reference="/foo/bar",
                                    ),
                                    RequisiteNode(
                                        start=Position(line=6, col=6),
                                        end=Position(line=6, col=25),
                                        module="service",
                                        reference="libvirtd",
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )
