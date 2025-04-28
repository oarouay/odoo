from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

class WebsiteSaleExtended(WebsiteSale):

    @http.route(['/shop/confirmation'], type='http', auth="public", website=True, sitemap=False)
    def shop_payment_confirmation(self, **post):
        """ End of checkout process controller. Confirmation is basically seeing
        the status of a sale.order. State at this point :
        - should not have any context / session info: clean them
        - take a sale.order id, because we request a sale.order and are not
          session dependent anymore
        """
        sale_order_id = request.session.get('sale_last_order_id')
        if sale_order_id:
            order = request.env['sale.order'].sudo().browse(sale_order_id)

            # Custom logic: Handle click tracking
            click_id = request.httprequest.cookies.get('odoo_click_id')
            if click_id:
                click = request.env['link.tracker.click'].sudo().browse(int(click_id))
                if click.exists() and not click.sale_id:
                    click.sale_id = order
                    order.tracker_click_id = click

            # Now call the base confirmation method
            return super(WebsiteSaleExtended, self).shop_payment_confirmation(**post)
        else:
            return request.redirect('/shop')
