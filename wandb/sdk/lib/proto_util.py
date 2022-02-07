import json


def dict_from_proto_list(obj_list):
    return {item.key: json.loads(item.value_json) for item in obj_list}
