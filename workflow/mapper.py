import json
from functools import reduce


def list_of_objects(data, old_key_path_list, new_key):
    """ 
    Handle case of list of objects :: [{}] 
    """
    existing_list = data.get(new_key)
    
    if existing_list is None:
        existing_list = data[new_key] = []
    
    for obj in existing_list:
        obj_iter = obj
        
        for old_key in old_key_path_list:
            if old_key not in obj_iter:
                return obj
            obj_iter = obj_iter[old_key]
        
    existing_list.append({})
    return existing_list[-1]


def get_nested(dictionary, keys):
    """ 
    Get value of nested dict levels. 
    """
    return reduce(
        lambda d, key: d.get(key, "") if isinstance(d, dict) else "", 
        keys, dictionary)


def set_nested(data, path):
    """ 
    Creates nested paths if necessary; returns last value in the sequence. 
    """
    iter = data
    for v in path:
        if iter.get(v) is None:
            iter[v] = {}
        iter = iter[v]
    
    return iter


def as_list(payload):
    """ 
    Returns payload as list.
    """
    return payload if isinstance(payload, list) else [payload]


class DataMapper:
    """
    Class for mapping JSON strings from one format to another.
    
    Mappings are provided in the form of a JSON string, where keys represent
    identifiers in the "source" document and values represent mappings to
    "destination" document.
    
    Values should be defined according to the following rules:
    - "&" tells the importer to move the value to another key:value.
    - ":" tells the importer to just nest keys.
    - "[]" tells the importer to create an list.
    - "{}" tells the importer to create an object.
    - "{}.somekey" tells the importer to create an object with somekey key.
    - "[{}]" tells the importer to create a list of objects.
    """
    
    def __init__(self, mapping_json_str):
        """
        :in mapping_json_str string in JSON format defining object mappings
        """
        self.mapping_dict, self.ignored_parts = \
                self._validate_mapping_json_str(mapping_json_str)

    def _validate_mapping_json_str(self, mapping_json_str):
        """
        :in mapping_json_str string in JSON format defining object mappings
        :out tuple consisting of a dictionary and the value for 'ignored_parts'.
        Will raise an exception in case mapping dictionary contains values which
        are not strings.
        """
        if isinstance(mapping_json_str, str):
            mapping_dict = json.loads(mapping_json_str)
        else:
            mapping_dict = mapping_json_str

        ignored_parts = mapping_dict.pop('ignored_parts', {})
        if not all(isinstance(v, str) for v in mapping_dict.values()):
            raise Exception("Input dictionary values should be strings.")
        return mapping_dict, ignored_parts
    
    def form_doc(self, from_json_str):
        """
        :in from_json_str document (as JSON string) which should be mapped according
            to self.mapping_dict rules.
        :out dictionary constructed by applying self.mapping_dict mappings to the
        from_json_str parameter, along with a key-value mapping ("ignored_parts": 
        self.ignored_parts)
        """
        return self.form_doc_dict(json.loads(from_json_str))
        
    def form_doc_dict(self, from_dict):
        """
        :in from_dict document (as dictionary) which should be mapped according
            to self.mapping_dict rules.
        :out dictionary constructed by applying self.mapping_dict mappings to the
        from_dict parameter, along with a key-value mapping ("ignored_parts": 
        self.ignored_parts)
        """
        
        data = {
            "ignored_parts": self.ignored_parts
        }

        for k, v in self.mapping_dict.items():
            parts = v.split('&')
            payload_path = k.split(':')
            payload = get_nested(from_dict, payload_path)

            if isinstance(payload, str):
                payload = payload.strip()

            for part in parts:
                new_path = part.split(':')
                new_doc = set_nested(data, new_path[:-1])             
                last = new_path.pop()

                if last.endswith('[{}]'):
                    for item in as_list(payload):
                        new_doc = list_of_objects(data, payload_path, last[:-4])
                        new_doc[payload_path[0]] = item
                elif last.startswith("{}"):
                    new_doc = set_nested(data, new_path[:-1])
                    key = payload_path[-1] if len(last) == 2 else last[3:]
                    new_path = [key] if len(payload_path) == 0 else payload_path
                    new_doc[new_path[-1]] = { key: payload }
                elif last.endswith('[]'):
                    last = last[:-2]
                    existing_list = new_doc.get(last)
                    if existing_list is None:
                        existing_list = new_doc[last] = []
                    existing_list.extend(as_list(payload))
                elif last.endswith('<int>'):
                    last = last[:-5]
                    new_doc[last] = int(payload)
                elif last.endswith('<str>'):
                    last = last[:-5]
                    new_doc[last] = str(payload)
                else:
                    new_doc[last] = payload

        return data
