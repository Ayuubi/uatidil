{
    'name': 'idil',
    'version': '1.0.0',
    'category': 'Idil',
    'summary': 'Idil Management System',
    'description': "Mohamed Dahir",
    'depends': ['mail', 'point_of_sale', 'web'],
    'application': True,
    'sequence': -100,
    'author': 'MSLTs',

    'assets': {
        'web.assets_common': [
            # 'idil/static/src/scss/primary_variables.scss',

        ],
        'point_of_sale.assets': [
            'idil/static/src/js/pos_customer_modification.js',
        ],
        'web.assets_backend': [
            'idil/static/src/css/kanban.css',

            # Include your new JS file here

        ],
        'web._assets_primary_variables': [
            ('prepend', 'idil/static/src/scss/primary_variables.scss'),
        ],

    },

    'data': [
        'security/ir.model.access.csv',
        'data/transaction_source_data.xml',

        'data/seq_journal_entry.xml',
        'data/groups.xml',
        'data/restaurant_chart_of_accounts.xml',
        'data/customer_types.xml',  # Reference to your XML data file
        'data/unit_measures.xml',  # Reference to your XML data file
        'data/item_categories.xml',  # Reference to your XML data file

        'data/idil_sequence.xml',
        'data/delete.xml',
        'data/booking_sequence.xml',
        'data/purchase_sequence.xml',
        'reports/report_placeorder.xml',

        'views/customer_view.xml',
        'views/vendor_view.xml',
        'views/custypes_view.xml',
        'views/item_view.xml',
        'views/unit_measure_view.xml',
        'views/item_category_view.xml',
        'views/chart_of_accounts_views.xml',
        'views/purchase_view.xml',
        'views/view__purchase_order.xml',
        'views/BOM.xml',
        'views/bom_type_view.xml',
        'views/product_views.xml',
        'views/view_manufacturing_order.xml',
        'reports/Account_balance_report.xml',
        'reports/Vendor_balance_report.xml',
        'reports/vendor_transaction_report.xml',
        'reports/Product_Stock_report.xml',
        'reports/sales_person_balance_report.xml',
        'views/vendor_bills.xml',
        'views/trx_source.xml',
        'views/sales.xml',
        'views/sales_staff.xml',
        'views/SalespersonPlaceOrder.xml',
        'views/sales_reciept_view.xml',
        'views/Sales_reciept.xml',
        'views/pos_menu_view.xml',
        'views/pos_session_view.xml',
        'views/pos_payment_method_views.xml',
        'views/idil_employee_views.xml',
        'views/kitchen_views.xml',
        'views/kitchen_transfer_views.xml',
        'views/view_trial_balance.xml',

        'views/kitchen_cook.xml',
        'views/transaction_booking_views.xml',
        'views/view_journal_entry.xml',
        'views/vendor_transaction_views.xml',

        'views/report_balance_sheet.xml',
        'views/report_income_statement.xml',

        'views/template_override.xml',

        'views/view_commission.xml',
        'views/CurrencyExchange.xml',
        'views/company_trial_balance.xml',
        'views/income_statement.xml',
        'views/idil_balance_sheet_report.xml',
        'views/sale_return.xml',
        'views/stock_adjustment_views.xml',
        'views/balance_sheet.xml',

        'views/menu.xml',
    ],
}
