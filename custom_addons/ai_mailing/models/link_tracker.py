from odoo import models, fields, api, _
from odoo.http import request
import werkzeug.utils
import urllib.parse
from werkzeug import urls

class LinkTracker(models.Model):
    _inherit = "link.tracker"

    # Add your custom fields
    label = fields.Char(string="Label", default="Default Label")
    campaign_id1 = fields.Many2one('marketing.campaign', string='Campaign', ondelete='set null')

    # Click statistics - already exists or is computed differently in base model
    # So we'll redefine or extend only what we need
    click_count = fields.Integer(string="Total Clicks", related="count", readonly=True)
    unique_click_count = fields.Integer(string="Unique Clicks", compute="_compute_unique_click_count", store=True)
    last_click_date = fields.Datetime(string="Last Click", compute="_compute_click_dates", store=True)
    first_click_date = fields.Datetime(string="First Click", compute="_compute_click_dates", store=True)
    short_url = fields.Char(string='Tracked URL', compute='_compute_short_url')
    click_ids = fields.One2many('link.tracker.click', 'link_id', string="Clicks")
    @api.constrains('url', 'campaign_id1', 'medium_id', 'source_id')
    def _check_unicity(self):
        pass

    @api.depends('url')
    def _compute_short_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for tracker in self:
            tracker.short_url = f"{base_url}/r/{tracker.id}" if tracker.id and tracker.url else False

    # Sales tracking - these are new fields

    @api.depends('link_click_ids')
    def _compute_unique_click_count(self):
        for tracker in self:
            tracker.unique_click_count = len(tracker.link_click_ids.mapped('ip'))

    @api.depends('link_click_ids')
    def _compute_click_dates(self):
        for tracker in self:
            clicks = tracker.link_click_ids
            if clicks:
                tracker.last_click_date = max(clicks.mapped('create_date'))
                tracker.first_click_date = min(clicks.mapped('create_date'))
            else:
                tracker.last_click_date = False
                tracker.first_click_date = False



    def redirect_action(self):
        """Handle link clicks and set tracking cookie"""
        self.ensure_one()
        click = self.env['link.tracker.click'].create({
            'link_id': self.id,
            'ip': request.httprequest.remote_addr,
            'user_agent': request.httprequest.user_agent.string,
        })

        response = werkzeug.utils.redirect(self.redirected_url)  # Use redirected_url from base class
        response.set_cookie('odoo_click_id', str(click.id), max_age=30 * 24 * 3600)  # 30 days
        return response



class LinkTrackerClick(models.Model):
    _inherit = "link.tracker.click"

    # Add new fields to the existing model
    user_agent = fields.Char(string="User Agent")
    source_id = fields.Many2one('utm.source', string="Source")
    medium_id = fields.Many2one('utm.medium', string="Medium")
    click_date = fields.Datetime(string="Click Time", default=fields.Datetime.now)
    link_id = fields.Many2one('link.tracker', string="Link", required=True, ondelete='cascade')

    # UTM fields - existing in base model or through inheritance
    mailing_trace_id = fields.Many2one('mailing.trace', string='Mailing Trace')
    # Geographic data - country_id already exists in base model
    city = fields.Char(string="City")

    # Device data
    device_type = fields.Selection([
        ('desktop', 'Desktop'),
        ('mobile', 'Mobile'),
        ('tablet', 'Tablet'),
        ('other', 'Other')
    ], string="Device Type")

    # Sale tracking
    sale_id = fields.Many2one('sale.order', string='Resulting Sale',ondelete='set null')
    converted = fields.Boolean(string='Converted to Sale', compute='_compute_converted', store=True)
    conversion_time = fields.Float(
        string='Conversion Time (hours)',
        compute='_compute_conversion_time',
        help="Time between click and sale in hours"
    )
    valid_conversion = fields.Boolean(
        string='Valid Conversion',
        compute='_compute_valid_conversion',
        help="Sale occurred within 30 days of click"
    )

    @api.depends('sale_id')
    def _compute_converted(self):
        for click in self:
            click.converted = bool(click.sale_id)

    @api.depends('create_date', 'sale_id.date_order')
    def _compute_conversion_time(self):
        for click in self:
            if click.sale_id and click.create_date:
                delta = click.sale_id.date_order - click.create_date
                click.conversion_time = delta.total_seconds() / 3600
            else:
                click.conversion_time = 0.0

    @api.depends('conversion_time')
    def _compute_valid_conversion(self):
        for click in self:
            click.valid_conversion = click.converted and click.conversion_time <= (30 * 24)  # 30 days in hours

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Add geo-IP data
            if 'ip' in vals and not vals.get('country_id'):
                geo_data = self._get_geoip_data(vals['ip'])
                if geo_data:
                    country = self.env['res.country'].search([('code', '=', geo_data.get('country_code'))], limit=1)
                    if country:
                        vals.update({
                            'country_id': country.id,
                            'city': geo_data.get('city')
                        })

            # Detect device type
            if 'user_agent' in vals and not vals.get('device_type'):
                vals['device_type'] = self._detect_device_type(vals['user_agent'])

        return super().create(vals_list)

    def _get_geoip_data(self, ip):
        """Get geographic data from IP address"""
        # In production, integrate with a geoIP service
        return {
            'country_code': 'US',
            'city': 'New York'
        }

    def _detect_device_type(self, user_agent):
        """Detect device type from user agent string"""
        user_agent = (user_agent or '').lower()
        if 'mobile' in user_agent:
            return 'mobile'
        elif 'tablet' in user_agent:
            return 'tablet'
        elif any(os in user_agent for os in ['windows', 'macintosh', 'linux']):
            return 'desktop'
        return 'other'