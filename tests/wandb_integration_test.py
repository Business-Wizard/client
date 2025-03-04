"""These test the full stack by launching a real backend server.  You won't get
credit for coverage of the backend logic in these tests.  See test_sender.py for testing
specific backend logic, or wandb_test.py for testing frontend logic.

Be sure to use `test_settings` or an isolated directory
"""

import wandb
import pytest
import json
import platform
import subprocess
import os
import sys
import shutil
from .utils import fixture_open
import sys

# Conditional imports of the reload function based on version
if sys.version_info.major == 2:
    reloadFn = reload  # noqa: F821
elif sys.version_info.minor >= 4:
    import importlib

    reloadFn = importlib.reload
else:
    import imp

    reloadFn = imp.reload


# TODO: better debugging, if the backend process fails to start we currently
# don't get any debug information even in the internal logs.  For now I'm writing
# logs from all tests that use test_settings to tests/logs/TEST_NAME.  If you're
# having tests just hang forever, I suggest running test/test_sender to see backend
# errors until we ensure we propogate the errors up.


def test_resume_allow_success(live_mock_server, test_settings):
    res = live_mock_server.set_ctx({"resume": True})
    print("CTX AFTER UPDATE", res)
    print("GET RIGHT AWAY", live_mock_server.get_ctx())
    wandb.init(reinit=True, resume="allow", settings=test_settings)
    wandb.log({"acc": 10})
    wandb.join()
    server_ctx = live_mock_server.get_ctx()
    print("CTX", server_ctx)
    first_stream_hist = server_ctx["file_stream"][0]["files"]["wandb-history.jsonl"]
    print(first_stream_hist)
    assert first_stream_hist["offset"] == 15
    assert json.loads(first_stream_hist["content"][0])["_step"] == 16
    # TODO: test _runtime offset setting
    # TODO: why no event stream?
    # assert first_stream['files']['wandb-events.jsonl'] == {
    #    'content': ['{"acc": 10, "_step": 15}'], 'offset': 0
    # }


@pytest.mark.skipif(
    platform.system() == "Windows", reason="File syncing is somewhat busted in windows"
)
# TODO: Sometimes wandb-summary.json didn't exists, other times requirements.txt in windows
def test_parallel_runs(live_mock_server, test_settings):
    with open("train.py", "w") as f:
        f.write(fixture_open("train.py").read())
    p1 = subprocess.Popen(["python", "train.py"], env=os.environ)
    p2 = subprocess.Popen(["python", "train.py"], env=os.environ)
    exit_codes = [p.wait() for p in (p1, p2)]
    assert exit_codes == [0, 0]
    num_runs = 0
    # Assert we've stored 2 runs worth of files
    # TODO: not confirming output.log because it is missing sometimes likely due to a BUG
    files_sorted = sorted(
        [
            "wandb-metadata.json",
            "code/tests/logs/test_parallel_runs/train.py",
            "requirements.txt",
            "config.yaml",
            "wandb-summary.json",
        ]
    )
    for run, files in live_mock_server.get_ctx()["storage"].items():
        num_runs += 1
        print("Files from server", files)
        assert (
            sorted([f for f in files if not f.endswith(".patch") and f != "output.log"])
            == files_sorted
        )
    assert num_runs == 2


def test_resume_must_failure(live_mock_server, test_settings):
    with pytest.raises(wandb.Error) as e:
        wandb.init(reinit=True, resume="must", settings=test_settings)
    assert "resume='must' but run" in e.value.message


def test_resume_never_failure(live_mock_server, test_settings):
    # TODO: this test passes independently but fails in the suite
    live_mock_server.set_ctx({"resume": True})
    print("CTX", live_mock_server.get_ctx())
    with pytest.raises(wandb.Error) as e:
        wandb.init(reinit=True, resume="never", settings=test_settings)
    assert "resume='never' but run" in e.value.message


def test_resume_auto_success(live_mock_server, test_settings):
    run = wandb.init(reinit=True, resume=True, settings=test_settings)
    run.join()
    assert not os.path.exists(test_settings.resume_fname)


def test_resume_auto_failure(live_mock_server, test_settings):
    test_settings.run_id = None
    with open(test_settings.resume_fname, "w") as f:
        f.write(json.dumps({"run_id": "resumeme"}))
    run = wandb.init(reinit=True, resume=True, settings=test_settings)
    assert run.id == "resumeme"
    run.join(exit_code=3)
    assert os.path.exists(test_settings.resume_fname)


def test_include_exclude_config_keys(live_mock_server, test_settings):
    config = {
        "foo": 1,
        "bar": 2,
        "baz": 3,
    }
    run = wandb.init(
        reinit=True,
        resume=True,
        settings=test_settings,
        config=config,
        config_exclude_keys=("bar",),
    )

    assert run.config["foo"] == 1
    assert run.config["baz"] == 3
    assert "bar" not in run.config
    run.join()

    run = wandb.init(
        reinit=True,
        resume=True,
        settings=test_settings,
        config=config,
        config_include_keys=("bar",),
    )
    assert run.config["bar"] == 2
    assert "foo" not in run.config
    assert "baz" not in run.config
    run.join()

    with pytest.raises(wandb.errors.error.UsageError):
        run = wandb.init(
            reinit=True,
            resume=True,
            settings=test_settings,
            config=config,
            config_exclude_keys=("bar",),
            config_include_keys=("bar",),
        )


def test_network_fault_files(live_mock_server, test_settings):
    live_mock_server.set_ctx({"fail_storage_times": 5})
    run = wandb.init(settings=test_settings)
    run.join()
    ctx = live_mock_server.get_ctx()
    print(ctx)
    assert [
        f
        for f in sorted(ctx["storage"][run.id])
        if not f.endswith(".patch") and not f.endswith(".py")
    ] == sorted(
        [
            "wandb-metadata.json",
            "requirements.txt",
            "config.yaml",
            "wandb-summary.json",
        ]
    )


def test_network_fault_graphql(live_mock_server, test_settings):
    # TODO: Initial login fails within 5 seconds so we fail after boot.
    run = wandb.init(settings=test_settings)
    live_mock_server.set_ctx({"fail_graphql_times": 5})
    run.join()
    ctx = live_mock_server.get_ctx()
    print(ctx)
    assert [
        f
        for f in sorted(ctx["storage"][run.id])
        if not f.endswith(".patch") and not f.endswith(".py")
    ] == sorted(
        [
            "wandb-metadata.json",
            "requirements.txt",
            "config.yaml",
            "wandb-summary.json",
        ]
    )


def _remove_dir_if_exists(path):
    """Recursively removes directory. Be careful"""
    if os.path.isdir(path):
        shutil.rmtree(path)


def test_dir_on_import(live_mock_server, test_settings):
    """Ensures that `import wandb` does not create a local storage directory"""
    default_path = os.path.join(os.getcwd(), "wandb")
    custom_env_path = os.path.join(os.getcwd(), "env_custom")

    if "WANDB_DIR" in os.environ:
        del os.environ["WANDB_DIR"]

    # Test for the base case
    _remove_dir_if_exists(default_path)
    reloadFn(wandb)
    assert not os.path.isdir(default_path), "Unexpected directory at {}".format(
        default_path
    )

    # test for the case that the env variable is set
    os.environ["WANDB_DIR"] = custom_env_path
    _remove_dir_if_exists(default_path)
    reloadFn(wandb)
    assert not os.path.isdir(default_path), "Unexpected directory at {}".format(
        default_path
    )
    assert not os.path.isdir(custom_env_path), "Unexpected directory at {}".format(
        custom_env_path
    )


def test_dir_on_init(live_mock_server, test_settings):
    """Ensures that `wandb.init()` creates the proper directory and nothing else"""
    default_path = os.path.join(os.getcwd(), "wandb")

    # Clear env if set
    if "WANDB_DIR" in os.environ:
        del os.environ["WANDB_DIR"]

    # Test for the base case
    reloadFn(wandb)
    _remove_dir_if_exists(default_path)
    run = wandb.init()
    run.join()
    assert os.path.isdir(default_path), "Expected directory at {}".format(default_path)


def test_dir_on_init_env(live_mock_server, test_settings):
    """Ensures that `wandb.init()` w/ env variable set creates the proper directory and nothing else"""
    default_path = os.path.join(os.getcwd(), "wandb")
    custom_env_path = os.path.join(os.getcwd(), "env_custom")

    # test for the case that the env variable is set
    os.environ["WANDB_DIR"] = custom_env_path
    if not os.path.isdir(custom_env_path):
        os.makedirs(custom_env_path)
    reloadFn(wandb)
    _remove_dir_if_exists(default_path)
    run = wandb.init()
    run.join()
    assert not os.path.isdir(default_path), "Unexpected directory at {}".format(
        default_path
    )
    assert os.path.isdir(custom_env_path), "Expected directory at {}".format(
        custom_env_path
    )
    # And for the duplicate-run case
    _remove_dir_if_exists(default_path)
    run = wandb.init()
    run.join()
    assert not os.path.isdir(default_path), "Unexpected directory at {}".format(
        default_path
    )
    assert os.path.isdir(custom_env_path), "Expected directory at {}".format(
        custom_env_path
    )
    del os.environ["WANDB_DIR"]


def test_dir_on_init_dir(live_mock_server, test_settings):
    """Ensures that `wandb.init(dir=DIR)` creates the proper directory and nothing else"""

    default_path = os.path.join(os.getcwd(), "wandb")
    dir_name = "dir_custom"
    custom_dir_path = os.path.join(os.getcwd(), dir_name)

    # test for the case that the dir is set
    reloadFn(wandb)
    _remove_dir_if_exists(default_path)
    if not os.path.isdir(custom_dir_path):
        os.makedirs(custom_dir_path)
    run = wandb.init(dir="./" + dir_name)
    run.join()
    assert not os.path.isdir(default_path), "Unexpected directory at {}".format(
        default_path
    )
    assert os.path.isdir(custom_dir_path), "Expected directory at {}".format(
        custom_dir_path
    )
    # And for the duplicate-run case
    _remove_dir_if_exists(default_path)
    run = wandb.init(dir=f'./{dir_name}')
    run.join()
    assert not os.path.isdir(default_path), "Unexpected directory at {}".format(
        default_path
    )
    assert os.path.isdir(custom_dir_path), "Expected directory at {}".format(
        custom_dir_path
    )


def test_version_upgraded(
    live_mock_server, test_settings, capsys, disable_console, restore_version
):
    wandb.__version__ = "0.10.2"
    run = wandb.init()
    run.finish()
    captured = capsys.readouterr()
    assert "is available!  To upgrade, please run:" in captured.err


def test_version_yanked(
    live_mock_server, test_settings, capsys, disable_console, restore_version
):
    wandb.__version__ = "0.10.0"
    run = wandb.init()
    run.finish()
    captured = capsys.readouterr()
    assert "WARNING wandb version 0.10.0 has been recalled" in captured.err


def test_version_retired(
    live_mock_server, test_settings, capsys, disable_console, restore_version
):
    wandb.__version__ = "0.9.99"
    run = wandb.init()
    run.finish()
    captured = capsys.readouterr()
    assert "ERROR wandb version 0.9.99 has been retired" in captured.err
