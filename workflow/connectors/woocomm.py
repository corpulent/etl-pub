import json
import decimal

from currency_converter import CurrencyConverter
from woocommerce import API as WooCommAPI

from ..utils import (
    RegexRemover,
    grouper,
)


class WooComm:
    def __init__(self, doc, **kwargs):
        """
        WooCommerce connector handling all requests to a WooCommerce shop.
        """
        self.doc = doc
        self.doc_data = doc['data']
        self.vars_mapped = {}

        wcapi = WooCommAPI(
            url=kwargs.get('url'),
            consumer_key=kwargs.get('consumer_key'),
            consumer_secret=kwargs.get('consumer_secret'),
            wp_api=True,
            version='wc/v2',
            timeout=150
        )

        self.wcapi = wcapi
    
    def _log_event(self, event):
        print(event)

    def _generate_custom_structure(self, data):
        custom = self.doc_data.get('custom')
        images = custom['images']
        category_mapper = custom['category_mapper']
        categories = []
        image_list = []

        if data['state'] == 'active':
            data['status'] = 'publish'
        else:
            data['status'] = 'pending'

        if images:
            if images == 'etsy':
                position_counter = 0

                for image_item in data['images']:
                    listing_image_id = image_item['listing_image_id']
                    image_url = image_item['url_fullxfull'].replace('https', 'http')

                    try:
                        if listing_image_id == data['main_image']['listing_image_id']:
                            image_list.append({'src': image_url, 'position': 0})
                            position_counter += 1

                            continue
                    except KeyError as e:
                        pass

                    image_list.append({'src': image_url, 'position': position_counter})
                    position_counter += 1

                data['images'] = image_list
        try:
            for tax_item in data['taxonomy_path']:
                if tax_item in category_mapper:
                    categories.append({'id': category_mapper[tax_item]})

            category_string = ', '.join(data['taxonomy_path'])

            if category_string in category_mapper:
                categories.append({'id': category_mapper[category_string]})
        except KeyError as e:
            pass

        data['categories'] = list({v['id']:v for v in categories}.values())
        data['images'] = image_list
        regex_list = [
            "([^.!?]*?(E|e)tsy.*?\.)(?!\d)",
            ".*.shop_home.*.",
            ".*.listing-shop.*.",
            ".*CHECK OUT THE MATCHING.*",
        ]
        remover = RegexRemover(regex_list)
        description = remover.handle(data['description'])
        data['description'] = description

        return data

    def _generate_attributes(self, data):
        data['attributes'] = []
        attributes_map = {}

        if len(data['products']) == 1:
            data['type'] = 'simple'
        else:
            data['type'] = 'variable'

            for product in data['products']:
                if type(product) is dict:
                    for product_value in product['property_values']:
                        attribute_name = product_value['property_name']
                        
                        if attribute_name not in attributes_map:
                            attributes_map[attribute_name] = []

                        for attribute_value in product_value['values']:
                            if attribute_value not in attributes_map[attribute_name]:
                                attributes_map[attribute_name].append(attribute_value)

        if attributes_map:
            for attributes_map_key in attributes_map:
                attribute = {
                    'name': '',
                    'visible': True,
                    'variation': True,
                    'options': []
                }

                attribute['name'] = attributes_map_key
                attribute['options'] = attributes_map[attributes_map_key]

                data['attributes'].append(attribute)

        return data

    def _generate_variations(self, data):
        create_obj = []

        for product in data['products']:
            if type(product) is dict:
                if product['property_values']:
                    attributes_map = {}

                    # Generate the attribute map to be used for all the
                    # offerings in this product set.
                    for product_value in product['property_values']:
                        attribute_name = product_value['property_name']
                    
                        if attribute_name not in attributes_map:
                            attributes_map[attribute_name] = []

                        for attribute_value in product_value['values']:
                            if attribute_value not in attributes_map[attribute_name]:
                                attributes_map[attribute_name].append(attribute_value)

                    for product_offering in product['offerings']:
                        variation = {
                            'regular_price': '',
                            'purchasable': True,
                            'stock_quantity': 0,
                            'attributes': [],
                        }
                        cconverter = CurrencyConverter()
                        amount = product_offering['price']['currency_formatted_raw']
                        currency_code = product_offering['price']['currency_code']
                        amount_in_usd = cconverter.convert(amount, currency_code, 'USD')
                        D = decimal.Decimal
                        cent = D('0.01')
                        x = D(amount_in_usd)
                        variation['regular_price'] = str(x.quantize(cent,rounding=decimal.ROUND_UP))
                        variation['stock_quantity'] = product_offering['quantity']

                        for attribute in attributes_map:
                            for attribute_value in attributes_map[attribute]:
                                attribute_obj = {
                                    'name': attribute,
                                    'option': attribute_value
                                }

                                variation['attributes'].append(attribute_obj)

                    create_obj.append(variation)

        data['create'] = create_obj

        return data

    def http_get(self, endpoint, offset, per_page):
        if offset:
            endpoint = "{}&per_page={}&offset={}".format(endpoint, per_page, offset)
        else:
            endpoint = "{}&per_page={}".format(endpoint, per_page)

        response = self.wcapi.get(endpoint)

        return response.json()

    def http_post(self, endpoint, data):
        if "variations/batch" in endpoint:
            attributes = data['create']

            if attributes:
                for i in grouper(attributes, 20):
                    chunked_list = list(filter(None.__ne__, i))
                    response = self.wcapi.post(endpoint, {'create': chunked_list})
            else:
                response = self.wcapi.post(endpoint, {'create': []})
        else:
            response = self.wcapi.post(endpoint, data)

        return {
            "endpoint": endpoint,
            "method": 'post',
            "req": data,
            "res": response.json()
        }

    def http_put(self, endpoint, temp_data):
        ret = []

        if isinstance(temp_data, list):
            for req_data in temp_data:
                endpoint = "{0}/{1}".format(endpoint, req_data['id'])

                response = self.wcapi.put(endpoint, req_data)

                ret.append({
                    "endpoint": endpoint,
                    "method": 'put',
                    "req": req_data,
                    "res": response.json()
                })
        else:
            endpoint = "{0}/{1}".format(endpoint, temp_data['id'])
            response = self.wcapi.put(endpoint, temp_data)

            ret.append({
                "endpoint": endpoint,
                "method": 'put',
                "req": temp_data,
                "res": response.json()
            })

        return ret

    def http_delete(self, endpoint):
        return self.wcapi.delete(endpoint)

    def http_options(self, endpoint):
        return self.wcapi.options(endpoint)
