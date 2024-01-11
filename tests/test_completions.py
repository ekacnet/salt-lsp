from types import SimpleNamespace

from lsprotocol.types import CompletionItem, CompletionList, TextDocumentItem

from conftest import MODULE_DOCS

TEST_FILE = """saltmaster.packages:
  pkg.installed:
    - pkgs:
      - salt-master

/srv/git/salt-states:
  file.:
    - target: /srv/salt

git -C /srv/salt pull -q:
  cron.:
    - user: root
    - minute: '*/5'
"""

TEST_FILE_STATE_NAME = """saltmaster.packages:
  pkg.installed:
    - pkgs:
      - salt-master

/srv/git/salt-states:
  

git -C /srv/salt pull -q:
  cron.:
    - user: root
    - minute: '*/5'
"""
TEST_FILE_PARAM = """saltmaster.packages:
  pkg.installed:
    - pkgs:
      - salt-master

/srv/git/salt-states:
  file.managed:
    -

git -C /srv/salt pull -q:
  cron.:
    - user: root
    - minute: '*/5'
"""


def test_complete_of_file(salt_client_server, file_name_completer):
    _, server = salt_client_server
    txt_doc = {
        "text_document": TextDocumentItem(
            uri="foo.sls", text=TEST_FILE, version=0, language_id="sls"
        ),
    }
    server.workspace.put_text_document(txt_doc["text_document"])

    complete, completions = server.complete_state_name(
        SimpleNamespace(
            **{
                **txt_doc,
                "position": SimpleNamespace(line=6, character=7),
                "context": SimpleNamespace(trigger_character="."),
            }
        )
    )

    expected_completions = [
        (submod_name, MODULE_DOCS[f"file.{submod_name}"])
        for submod_name in file_name_completer["file"].state_sub_names
    ]
    assert completions == expected_completions
    assert complete is True


def test_complete_of_file_no_trigger(salt_client_server, file_name_completer):
    _, server = salt_client_server
    txt_doc = {
        "text_document": TextDocumentItem(
            uri="foo.sls", text=TEST_FILE, version=0, language_id="sls"
        ),
    }
    server.workspace.put_text_document(txt_doc["text_document"])

    complete, completions = server.complete_state_name(
        SimpleNamespace(
            **{
                **txt_doc,
                "position": SimpleNamespace(line=6, character=7),
            }
        )
    )

    expected_completions = [
        (submod_name, MODULE_DOCS[f"file.{submod_name}"])
        for submod_name in file_name_completer["file"].state_sub_names
    ]
    assert completions == expected_completions
    assert complete is True


def test_complete_of_statename_no_trigger(salt_client_server, file_name_completer):
    _, server = salt_client_server
    txt_doc = {
        "text_document": TextDocumentItem(
            uri="foo.sls", text=TEST_FILE_STATE_NAME, version=0, language_id="sls"
        ),
    }
    server.workspace.put_text_document(txt_doc["text_document"])

    completion_list = server.completions(
        SimpleNamespace(
            **{
                **txt_doc,
                "position": SimpleNamespace(line=6, character=3),
                "context": None,
            }
        )
    )

    expected_completions = CompletionList(
        is_incomplete=False,
        items=[CompletionItem(label="file", documentation=MODULE_DOCS["file"])],
    )
    assert completion_list == expected_completions
    assert completion_list.is_incomplete is False


def test_complete_of_params(salt_client_server, file_name_completer):
    _, server = salt_client_server
    txt_doc = {
        "text_document": TextDocumentItem(
            uri="foo.sls", text=TEST_FILE_PARAM, version=0, language_id="sls"
        ),
    }
    server.workspace.put_text_document(txt_doc["text_document"])

    completion_list = server.completions(
        SimpleNamespace(
            **{
                **txt_doc,
                "position": SimpleNamespace(line=7, character=5),
                "context": None,
            }
        )
    )

    expected_completions = [
        (param_name, None)
        for param_name in file_name_completer["file"].provide_param_completion(
            "managed"
        )
    ]
    expected_completion_list = CompletionList(
        is_incomplete=False,
        items=[
            CompletionItem(label=label, documentation=doc)
            for label, doc in expected_completions
        ],
    )
    assert completion_list == expected_completion_list
