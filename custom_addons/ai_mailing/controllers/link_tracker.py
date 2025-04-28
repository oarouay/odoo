from odoo import http
from odoo.http import request
from datetime import timedelta
from odoo import fields

class LinkTrackerController(http.Controller):

    @http.route('/r/<string:link_code>', type='http', auth="public", website=True)
    def track_link(self, link_code, **kwargs):
        """Handle link clicks with duplicate prevention"""
        tracker = request.env['link.tracker'].sudo().search([('id', '=', link_code)], limit=1)

        if not tracker:
            return request.not_found()

        # Get request data for tracking
        ip = request.httprequest.remote_addr
        user_agent = request.httprequest.user_agent.string

        # Check for existing clicks (duplicate prevention)
        click = request.env['link.tracker.click'].sudo().search([
            ('link_id', '=', tracker.id),
            '|',
            ('ip', '=', ip),
            ('user_agent', '=', user_agent),
            ('click_date', '>=', fields.Datetime.now() - timedelta(seconds=10))
        ], limit=1)

        if not click:
            # Create click record only if not a duplicate
            click_vals = {
                'link_id': tracker.id,
                'ip': ip,
                'user_agent': user_agent,
                'source_id': tracker.source_id.id,
                'medium_id': tracker.medium_id.id,
                'campaign_id': tracker.campaign_id.id,
                'click_date': fields.Datetime.now(),
            }
            click = request.env['link.tracker.click'].sudo().create(click_vals)
        # Redirect to original URL
        response = request.redirect(tracker.url)
        response.set_cookie('odoo_click_id', str(click.id), max_age=60 * 60 * 24 * 7)
        return response
