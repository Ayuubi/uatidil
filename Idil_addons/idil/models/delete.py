from odoo import models, fields, api
import logging


class ModelA(models.Model):
    _name = 'model.a'
    _description = 'Model A'

    _logger = logging.getLogger(__name__)

    # Other fields definition

    @api.model
    def delete_other_models_data(self, *args, **kwargs):
        models_to_delete = [
            'idil.sale.return.line',
            'idil.sale.return',

            'idil.sales.receipt',

            'idil.sale.order.line',
            'idil.sale.order',

            'idil.salesperson.place.order',
            'idil.salesperson.place.order.line',

            'idil.item.movement',

            'idil.vendor.payment',

            'idil.commission.payment',
            'idil.commission',
            'idil.vendor.transaction',

            'idil.purchase.order.line',
            'idil.purchase.order',

            'idil.journal.entry.line',
            'idil.journal.entry',

            'idil.kitchen.cook.line',
            'idil.kitchen.cook.process',

            'idil.kitchen.transfer.line',
            'idil.kitchen.transfer',

            'idil.salesperson.transaction',
            'idil.product.movement',
            'idil.salesperson.order.summary',

            'idil.currency.exchange',

            'idil.manufacturing.order.line',
            'idil.manufacturing.order',

            'idil.transaction.bookingline',
            'idil.transaction.booking',

        ]

        deletion_summary = []
        # Set all item quantities to zero
        try:
            items = self.env['idil.item'].search([])
            if items:
                item_count = len(items)
                items.write({'quantity': 0})
                message = f"Set quantity to zero for {item_count} items in idil.item."
                self._logger.info(message)
                deletion_summary.append(message)
            else:
                message = "No items found in idil.item to update."
                self._logger.info(message)
                deletion_summary.append(message)
        except Exception as e:
            message = f"Error updating item quantities: {e}"
            self._logger.error(message)
            deletion_summary.append(message)

        # Set all product stock quantities to zero
        try:
            products = self.env['my_product.product'].search([])
            if products:
                product_count = len(products)
                products.write({'stock_quantity': 0})
                message = f"Set stock quantity to zero for {product_count} products in my_product.product."
                self._logger.info(message)
                deletion_summary.append(message)
            else:
                message = "No products found in my_product.product to update."
                self._logger.info(message)
                deletion_summary.append(message)
        except Exception as e:
            message = f"Error updating product stock quantities: {e}"
            self._logger.error(message)
            deletion_summary.append(message)

        for model_name in models_to_delete:
            try:
                records = self.env[model_name].search([])
                if records:
                    record_count = len(records)
                    records.unlink()
                    message = f"Successfully deleted {record_count} records from {model_name}."
                    self._logger.info(message)
                    deletion_summary.append(message)
                else:
                    message = f"No records found in {model_name} to delete."
                    self._logger.info(message)
                    deletion_summary.append(message)
            except Exception as e:
                message = f"Error deleting records from {model_name}: {e}"
                self._logger.error(message)
                deletion_summary.append(message)

        # Join the summary into a single string to return
        return "\n".join(deletion_summary)

    @api.model
    def delete_other_models_setup(self, *args, **kwargs):
        models_to_delete = [
            'idil.bom.line',
            'idil.bom',

            'idil.bom.type',

            'idil.customer.type.registration',
            'idil.customer.registration',

            'idil.item',
            'idil.unit.measure',
            'idil.item.category',

            'idil.kitchen',
            'idil.payment.method',

            'my_product.product',
            'idil.sales.sales_personnel',

            'idil.vendor.registration',

            'idil.chart.account',
            'idil.chart.account.subheader',
            'idil.chart.account.header',

        ]

        deletion_summary = []

        for model_name in models_to_delete:
            try:
                records = self.env[model_name].search([])
                if records:
                    record_count = len(records)
                    records.unlink()
                    message = f"Successfully deleted {record_count} records from {model_name}."
                    self._logger.info(message)
                    deletion_summary.append(message)
                else:
                    message = f"No records found in {model_name} to delete."
                    self._logger.info(message)
                    deletion_summary.append(message)
            except Exception as e:
                message = f"Error deleting records from {model_name}: {e}"
                self._logger.error(message)
                deletion_summary.append(message)

        # Join the summary into a single string to return
        return "\n".join(deletion_summary)
