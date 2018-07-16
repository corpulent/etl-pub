from . import mapper


def form_doc(doc, mapping_json_str):
    new_mapper = mapper.DataMapper(mapping_json_str)
    data = new_mapper.form_doc_dict(doc)

    return data
