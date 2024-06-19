from odoo import models, fields, api


class PosCustomProduct(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _loader_params_product_product(self):
        return {
            'search_params': {
                'fields': [
                    'id', 'name', 'display_name', 'sale_price', 'taxes_id',
                    'barcode', 'internal_reference', 'type', 'uom_id', 'sales_description',
                    'category_id', 'stock_quantity', 'available_in_pos'
                ],
                'domain': [('available_in_pos', '=', True)],
                'context': {'display_default_code': False},  # Ensure context is set
            },
        }

    def _get_products_from_ui(self, product_ids):
        params = self._loader_params_product_product()['search_params']
        context = params.get('context', {})
        fields = params['fields']
        products = self.env['my_product.product'].with_context(**context).search_read([('id', 'in', product_ids)],
                                                                                      fields)
        return products

    def _load_model(self, model_name):
        # Ensure context is always present
        params = self._loader_params_product_product()['search_params']
        context = params.get('context', {})
        self = self.with_context(**context)
        return super(PosCustomProduct, self)._load_model(model_name)
