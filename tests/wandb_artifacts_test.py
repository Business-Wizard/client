import os
import pytest
from wandb import util
import wandb
import platform
import shutil
import wandb.data_types as data_types
import numpy as np


def mock_boto(artifact, path=False):
    class S3Object(object):
        def __init__(self, name="my_object.pb", metadata=None):
            self.metadata = metadata or {"md5": "1234567890abcde"}
            self.e_tag = '"1234567890abcde"'
            self.version_id = "1"
            self.name = name
            self.key = name
            self.content_length = 10

        def load(self):
            if path:
                raise util.get_module("botocore").exceptions.ClientError(
                    {"Error": {"Code": "404"}}, "HeadObject"
                )

    class Filtered(object):
        def limit(self, *args, **kwargs):
            return [S3Object(), S3Object(name="my_other_object.pb")]

    class S3Objects(object):
        def filter(self, **kwargs):
            return Filtered()

    class S3Bucket(object):
        def __init__(self, *args, **kwargs):
            self.objects = S3Objects()

    class S3Resource(object):
        def Object(self, bucket, key):
            return S3Object()

        def Bucket(self, bucket):
            return S3Bucket()

    mock = S3Resource()
    handler = artifact._storage_policy._handler._handlers["s3"]
    handler._s3 = mock
    handler._botocore = util.get_module("botocore")
    return mock


def mock_gcs(artifact, path=False):
    class Blob(object):
        def __init__(self, name="my_object.pb", metadata=None):
            self.md5_hash = "1234567890abcde"
            self.etag = "1234567890abcde"
            self.generation = "1"
            self.name = name
            self.size = 10

    class GSBucket(object):
        def get_blob(self, *args, **kwargs):
            return None if path else Blob()

        def list_blobs(self, *args, **kwargs):
            return [Blob(), Blob(name="my_other_object.pb")]

    class GSClient(object):
        def bucket(self, bucket):
            return GSBucket()

    mock = GSClient()
    handler = artifact._storage_policy._handler._handlers["gs"]
    handler._client = mock
    return mock


def mock_http(artifact, path=False, headers={}):
    class Response(object):
        def __init__(self, headers):
            self.headers = headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def raise_for_status(self):
            pass

    class Session(object):
        def __init__(self, name="file1.txt", headers=headers):
            self.headers = headers

        def get(self, path, *args, **kwargs):
            return Response(self.headers)

    mock = Session()
    handler = artifact._storage_policy._handler._handlers["http"]
    handler._session = mock
    return mock


def test_add_one_file(runner):
    with runner.isolated_filesystem():
        with open("file1.txt", "w") as f:
            f.write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_file("file1.txt")

        assert artifact.digest == "a00c2239f036fb656c1dcbf9a32d89b4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "size": 5,
        }


def test_add_named_file(runner):
    with runner.isolated_filesystem():
        with open("file1.txt", "w") as f:
            f.write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_file("file1.txt", name="great-file.txt")

        assert artifact.digest == "585b9ada17797e37c9cbab391e69b8c5"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["great-file.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "size": 5,
        }


def test_add_new_file(runner):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        with artifact.new_file("file1.txt") as f:
            f.write("hello")

        assert artifact.digest == "a00c2239f036fb656c1dcbf9a32d89b4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "size": 5,
        }


def test_add_dir(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_dir(".")

        assert artifact.digest == "a00c2239f036fb656c1dcbf9a32d89b4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "size": 5,
        }


def test_add_named_dir(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_dir(".", name="subdir")

        if platform.system() == "Windows":
            digest = "84eb4e81b4fe7ef81bd13971c6f80cdc"
        else:
            digest = "a757208d042e8627b2970d72a71bed5b"

        assert artifact.digest == digest

        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"][os.path.join("subdir", "file1.txt")] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "size": 5,
        }


def test_add_reference_local_file(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_reference("file://file1.txt")

        assert artifact.digest == "a00c2239f036fb656c1dcbf9a32d89b4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "ref": "file://file1.txt",
            "size": 5,
        }


def test_add_reference_local_file_no_checksum(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_reference("file://file1.txt", checksum=False)

        assert artifact.digest == "2f66dd01e5aea4af52445f7602fe88a0"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "file://file1.txt",
            "ref": "file://file1.txt",
        }


def test_add_reference_local_dir(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        open("file2.txt", "w").write("dude")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_reference("file://" + os.getcwd())

        assert artifact.digest == "5e8e98ebd59cc93b58d0cb26432d4720"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "ref": "file://" + os.path.join(os.getcwd(), "file1.txt"),
            "size": 5,
        }
        assert manifest["contents"]["file2.txt"] == {
            "digest": "E7c+2uhEOZC+GqjxpIO8Jw==",
            "ref": "file://" + os.path.join(os.getcwd(), "file2.txt"),
            "size": 4,
        }


def test_add_s3_reference_object(runner, mocker):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_boto(artifact)
        artifact.add_reference("s3://my-bucket/my_object.pb")

        assert artifact.digest == "8aec0d6978da8c2b0bf5662b3fd043a4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["my_object.pb"] == {
            "digest": "1234567890abcde",
            "ref": "s3://my-bucket/my_object.pb",
            "extra": {"etag": "1234567890abcde", "versionID": "1"},
            "size": 10,
        }


def test_add_s3_reference_object_with_name(runner, mocker):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_boto(artifact)
        artifact.add_reference("s3://my-bucket/my_object.pb", name="renamed.pb")

        assert artifact.digest == "bd85fe009dc9e408a5ed9b55c95f47b2"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["renamed.pb"] == {
            "digest": "1234567890abcde",
            "ref": "s3://my-bucket/my_object.pb",
            "extra": {"etag": "1234567890abcde", "versionID": "1"},
            "size": 10,
        }


def test_add_s3_reference_path(runner, mocker, capsys):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_boto(artifact, path=True)
        artifact.add_reference("s3://my-bucket/")

        assert artifact.digest == "17955d00a20e1074c3bc96c74b724bfe"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["my_object.pb"] == {
            "digest": "1234567890abcde",
            "ref": "s3://my-bucket/my_object.pb",
            "extra": {"etag": "1234567890abcde", "versionID": "1"},
            "size": 10,
        }
        _, err = capsys.readouterr()
        assert "Generating checksum" in err


def test_add_s3_max_objects(runner, mocker, capsys):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_boto(artifact, path=True)
        with pytest.raises(ValueError):
            artifact.add_reference("s3://my-bucket/", max_objects=1)


def test_add_reference_s3_no_checksum(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        # TODO: Should we require name in this case?
        artifact.add_reference("s3://my_bucket/file1.txt", checksum=False)

        assert artifact.digest == "52631787ed3579325f985dc0f2374040"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "s3://my_bucket/file1.txt",
            "ref": "s3://my_bucket/file1.txt",
        }


def test_add_gs_reference_object(runner, mocker):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_gcs(artifact)
        artifact.add_reference("gs://my-bucket/my_object.pb")

        assert artifact.digest == "8aec0d6978da8c2b0bf5662b3fd043a4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["my_object.pb"] == {
            "digest": "1234567890abcde",
            "ref": "gs://my-bucket/my_object.pb",
            "extra": {"etag": "1234567890abcde", "versionID": "1"},
            "size": 10,
        }


def test_add_gs_reference_object_with_name(runner, mocker):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_gcs(artifact)
        artifact.add_reference("gs://my-bucket/my_object.pb", name="renamed.pb")

        assert artifact.digest == "bd85fe009dc9e408a5ed9b55c95f47b2"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["renamed.pb"] == {
            "digest": "1234567890abcde",
            "ref": "gs://my-bucket/my_object.pb",
            "extra": {"etag": "1234567890abcde", "versionID": "1"},
            "size": 10,
        }


def test_add_gs_reference_path(runner, mocker, capsys):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_gcs(artifact, path=True)
        artifact.add_reference("gs://my-bucket/")

        assert artifact.digest == "17955d00a20e1074c3bc96c74b724bfe"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["my_object.pb"] == {
            "digest": "1234567890abcde",
            "ref": "gs://my-bucket/my_object.pb",
            "extra": {"etag": "1234567890abcde", "versionID": "1"},
            "size": 10,
        }
        _, err = capsys.readouterr()
        assert "Generating checksum" in err


def test_add_http_reference_path(runner):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        mock_http(artifact, headers={"ETag": '"abc"', "Content-Length": "256",})
        artifact.add_reference("http://example.com/file1.txt")

        assert artifact.digest == "48237ccc050a88af9dcd869dd5a7e9f4"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["file1.txt"] == {
            "digest": "abc",
            "ref": "http://example.com/file1.txt",
            "size": 256,
            "extra": {"etag": '"abc"',},
        }


def test_add_reference_named_local_file(runner):
    with runner.isolated_filesystem():
        open("file1.txt", "w").write("hello")
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_reference("file://file1.txt", name="great-file.txt")

        assert artifact.digest == "585b9ada17797e37c9cbab391e69b8c5"
        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["great-file.txt"] == {
            "digest": "XUFAKrxLKna5cZ2REBfFkg==",
            "ref": "file://file1.txt",
            "size": 5,
        }


def test_add_reference_unknown_handler(runner):
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_reference("ref://example.com/somefile.txt", name="ref")

        assert artifact.digest == "410ade94865e89ebe1f593f4379ac228"

        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"]["ref"] == {
            "digest": "ref://example.com/somefile.txt",
            "ref": "ref://example.com/somefile.txt",
        }


def test_add_obj_wbimage_no_classes(runner):
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "2x2.png")
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        wb_image = wandb.Image(
            im_path,
            masks={
                "ground_truth": {
                    "path": os.path.join(test_folder, "..", "assets", "2x2.png"),
                },
            },
        )
        with pytest.raises(ValueError):
            artifact.add(wb_image, "my-image")


def test_add_obj_wbimage(runner):
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "2x2.png")
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        wb_image = wandb.Image(im_path, classes=[{"id": 0, "name": "person"}])
        artifact.add(wb_image, "my-image")

        manifest = artifact.manifest.to_manifest_json()
        if os.name == "nt":  # windows
            assert artifact.digest == "c72784d4c7f230a79cf8139dce983188"
            assert manifest["contents"] == {
                "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
                "media\\images\\2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-image.image-file.json": {
                    "digest": "nD/QMrasZLE2Cp35MmshSg==",
                    "size": 198,
                },
            }
        else:
            assert artifact.digest == "c2e72e6e5261043b8d03461576f8ff88"
            assert manifest["contents"] == {
                "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
                "media/images/2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-image.image-file.json": {
                    "digest": "UhZfZLPavGE2tBRdTvIl3Q==",
                    "size": 196,
                },
            }


def test_add_obj_wbimage_classes_obj(runner):
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "2x2.png")
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        classes = wandb.Classes([{"id": 0, "name": "person"}])
        wb_image = wandb.Image(im_path, classes=classes)
        artifact.add(wb_image, "my-image")

        manifest = artifact.manifest.to_manifest_json()
        if os.name == "nt":  # windows
            assert manifest["contents"] == {
                "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
                "media\\images\\2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-image.image-file.json": {
                    "digest": "nD/QMrasZLE2Cp35MmshSg==",
                    "size": 198,
                },
            }
        else:
            assert manifest["contents"] == {
                "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
                "media/images/2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-image.image-file.json": {
                    "digest": "UhZfZLPavGE2tBRdTvIl3Q==",
                    "size": 196,
                },
            }


def test_add_obj_wbimage_classes_obj_already_added(runner):
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "2x2.png")
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        classes = wandb.Classes([{"id": 0, "name": "person"}])
        artifact.add(classes, "my-classes")
        wb_image = wandb.Image(im_path, classes=classes)
        artifact.add(wb_image, "my-image")

        manifest = artifact.manifest.to_manifest_json()
        if os.name == "nt":  # windows
            assert manifest["contents"] == {
                "my-classes.classes.json": {
                    "digest": "eG00DqdCcCBqphilriLNfw==",
                    "size": 64,
                },
                "media\\images\\2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-image.image-file.json": {
                    "digest": "9pCnyQxcBiuNIEzlB0nEYw==",
                    "size": 209,
                },
            }
        else:
            assert manifest["contents"] == {
                "my-classes.classes.json": {
                    "digest": "eG00DqdCcCBqphilriLNfw==",
                    "size": 64,
                },
                "media/images/2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-image.image-file.json": {
                    "digest": "jhtqSTpnbQyr2sL775eEkQ==",
                    "size": 207,
                },
            }


def test_add_obj_wbimage_image_already_added(runner):
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "2x2.png")
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        artifact.add_file(im_path)
        wb_image = wandb.Image(im_path, classes=[{"id": 0, "name": "person"}])
        artifact.add(wb_image, "my-image")

        manifest = artifact.manifest.to_manifest_json()
        assert manifest["contents"] == {
            "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
            "2x2.png": {"digest": "L1pBeGPxG+6XVRQk4WuvdQ==", "size": 71},
            "my-image.image-file.json": {
                "digest": "Wr7bZ9hy0p7Yc9eYRbSuvg==",
                "size": 183,
            },
        }


def test_add_obj_wbtable_images(runner):
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "2x2.png")
    with runner.isolated_filesystem():
        artifact = wandb.Artifact(type="dataset", name="my-arty")
        wb_image = wandb.Image(im_path, classes=[{"id": 0, "name": "person"}])
        wb_table = wandb.Table(["examples"])
        wb_table.add_data(wb_image)
        wb_table.add_data(wb_image)
        artifact.add(wb_table, "my-table")

        manifest = artifact.manifest.to_manifest_json()
        if os.name == "nt":  # windows
            assert manifest["contents"] == {
                "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
                "media\\images\\2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-table.table.json": {
                    "digest": "sFp8mwHHWFt75ovTLq3c+g==",
                    "size": 463,
                },
            }
        else:
            assert manifest["contents"] == {
                "classes.json": {"digest": "eG00DqdCcCBqphilriLNfw==", "size": 64},
                "media/images/2x2.png": {
                    "digest": "L1pBeGPxG+6XVRQk4WuvdQ==",
                    "size": 71,
                },
                "my-table.table.json": {
                    "digest": "TZhMeYO9IF2WvpKp4/mNDg==",
                    "size": 459,
                },
            }


def _make_wandb_image(suffix=""):
    classes = [
        {"id": 0, "name": "tree"},
        {"id": 1, "name": "car"},
        {"id": 3, "name": "road"},
    ]
    class_labels = {1: "tree", 2: "car", 3: "road"}
    test_folder = os.path.dirname(os.path.realpath(__file__))
    im_path = os.path.join(test_folder, "..", "assets", "test{}.png".format(suffix))
    return wandb.Image(
        im_path,
        classes=classes,
        boxes={
            "predictions": {
                "box_data": [
                    {
                        "position": {
                            "minX": 0.1,
                            "maxX": 0.2,
                            "minY": 0.3,
                            "maxY": 0.4,
                        },
                        "class_id": 1,
                        "box_caption": "minMax(pixel)",
                        "scores": {"acc": 0.1, "loss": 1.2},
                    },
                    {
                        "position": {
                            "minX": 0.1,
                            "maxX": 0.2,
                            "minY": 0.3,
                            "maxY": 0.4,
                        },
                        "class_id": 2,
                        "box_caption": "minMax(pixel)",
                        "scores": {"acc": 0.1, "loss": 1.2},
                    },
                ],
                "class_labels": class_labels,
            },
            "ground_truth": {
                "box_data": [
                    {
                        "position": {
                            "minX": 0.1,
                            "maxX": 0.2,
                            "minY": 0.3,
                            "maxY": 0.4,
                        },
                        "class_id": 1,
                        "box_caption": "minMax(pixel)",
                        "scores": {"acc": 0.1, "loss": 1.2},
                    },
                    {
                        "position": {
                            "minX": 0.1,
                            "maxX": 0.2,
                            "minY": 0.3,
                            "maxY": 0.4,
                        },
                        "class_id": 2,
                        "box_caption": "minMax(pixel)",
                        "scores": {"acc": 0.1, "loss": 1.2},
                    },
                ],
                "class_labels": class_labels,
            },
        },
        masks={
            "predictions": {
                "mask_data": np.random.randint(0, 4, size=(30, 30)),
                "class_labels": class_labels,
            },
            "ground_truth": {"path": im_path, "class_labels": class_labels},
        },
    )


def _make_wandb_table():
    return wandb.Table(
        columns=["id", "bool", "int", "float", "Image"],
        data=[
            ["string", True, 1, 1.4, _make_wandb_image()],
            ["string2", False, -0, -1.4, _make_wandb_image("2")],
        ],
    )


def _make_wandb_joinedtable():
    return wandb.JoinedTable(_make_wandb_table(), _make_wandb_table(), "id")


def simulate_artifact_download(artifact):
    # Simulate download
    for entry_name in artifact._manifest.entries:
        entry = artifact._manifest.entries[entry_name]
        target_path = os.path.join(
            artifact._artifact_dir.name, os.path.dirname(entry.path)
        )
        target_file = os.path.join(artifact._artifact_dir.name, entry.path)
        if entry.local_path != target_file and not os.path.exists(target_file):
            if not os.path.exists(target_path):
                os.makedirs(target_path)
            shutil.copy(entry.local_path, target_file)


def assert_json_serialization(obj):
    artifact = wandb.Artifact("artifact", "db")
    # artifact.add(obj, "name")
    expected_dict = obj.to_json(artifact)
    simulate_artifact_download(artifact)

    obj_copy = obj.__class__.from_json(expected_dict, artifact._artifact_dir.name)
    assert obj == obj_copy


def test_table_json_serialization(runner):
    assert_json_serialization(_make_wandb_table())


def test_image_json_serialization(runner):
    assert_json_serialization(_make_wandb_image())


def test_joinedtable_json_serialization(runner):
    assert_json_serialization(_make_wandb_joinedtable())
