import logging
from odoo import models, fields, api
from datetime import timedelta
import json

_logger = logging.getLogger(__name__)


class MarketingDashboard(models.Model):
    _name = 'marketing.dashboard'
    _description = 'Marketing Campaign Dashboard'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Basic Fields
    name = fields.Char(string="Dashboard Name", required=True, tracking=True,
                       default="New Dashboard", copy=False)
    active = fields.Boolean(default=True, tracking=True)
    last_refresh = fields.Datetime(string="Last Refreshed", readonly=True, default=fields.Datetime.now)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id.id)
    note = fields.Html(string="Notes")

    # Filter Fields
    date_from = fields.Date(string="From Date",
                            default=lambda self: fields.Date.start_of(fields.Date.today(), 'month'),
                            tracking=True)
    date_to = fields.Date(string="To Date",
                          default=lambda self: fields.Date.end_of(fields.Date.today(), 'month'),
                          tracking=True)

    marketing_campaign_ids = fields.Many2many('marketing.campaign', string="Marketing Campaigns", tracking=True)
    channel_ids = fields.Many2many('utm.source', string="Filter Channels", tracking=True)
    medium_ids = fields.Many2many('utm.medium', string="Filter Mediums", tracking=True)

    # Comparison period fields
    comparison_date_from = fields.Date(string="Comparison From", readonly=True)
    comparison_date_to = fields.Date(string="Comparison To", readonly=True)

    # Computed Metrics
    total_clicks = fields.Integer(string="Total Clicks", compute='_compute_metrics', store=True)
    unique_clicks = fields.Integer(string="Unique Clicks", compute='_compute_metrics', store=True)
    conversion_rate = fields.Float(string="Conversion Rate", compute='_compute_metrics', store=True)
    total_sales = fields.Integer(string="Total Sales", compute='_compute_metrics', store=True)
    total_revenue = fields.Monetary(string="Total Revenue", compute='_compute_metrics',
                                    currency_field='currency_id', store=True)
    avg_order_value = fields.Monetary(string="Avg. Order Value", compute='_compute_metrics',
                                      currency_field='currency_id', store=True)

    # Previous period metrics for comparison
    prev_total_clicks = fields.Integer(string="Previous Clicks", readonly=True)
    prev_unique_clicks = fields.Integer(string="Previous Unique Clicks", readonly=True)
    prev_conversion_rate = fields.Float(string="Previous Conversion Rate", readonly=True)
    prev_total_sales = fields.Integer(string="Previous Sales", readonly=True)
    prev_total_revenue = fields.Monetary(string="Previous Revenue", currency_field='currency_id', readonly=True)
    prev_avg_order_value = fields.Monetary(string="Previous AOV", currency_field='currency_id', readonly=True)

    # Trend indicators (percentage change)
    click_trend = fields.Float(string="Click Trend", compute='_compute_trends', store=True)
    unique_click_trend = fields.Float(string="Unique Click Trend", compute='_compute_trends', store=True)
    conversion_trend = fields.Float(string="Conversion Trend", compute='_compute_trends', store=True)
    sales_trend = fields.Float(string="Sales Trend", compute='_compute_trends', store=True)
    revenue_trend = fields.Float(string="Revenue Trend", compute='_compute_trends', store=True)
    aov_trend = fields.Float(string="AOV Trend", compute='_compute_trends', store=True)

    # Chart Data Fields
    daily_clicks_data = fields.Text(string="Daily Clicks Data", compute='_compute_chart_data')
    channel_performance_data = fields.Text(string="Channel Performance Data", compute='_compute_chart_data')
    campaign_revenue_data = fields.Text(string="Campaign Revenue Data", compute='_compute_chart_data')
    conversion_by_medium_data = fields.Text(string="Conversion by Medium Data", compute='_compute_chart_data')

    # Additional KPIs
    bounce_rate = fields.Float(string="Bounce Rate", compute='_compute_metrics', store=True)
    cac = fields.Monetary(string="Customer Acquisition Cost", compute='_compute_metrics',
                          currency_field='currency_id', store=True)
    roi = fields.Float(string="Return on Investment", compute='_compute_metrics', store=True)

    # New fields for click-based sales tracking
    total_click_sourced_sales = fields.Integer(string="Click-Sourced Sales", compute='_compute_metrics', store=True)
    avg_time_to_purchase = fields.Float(string="Avg Time to Purchase (hours)", compute='_compute_metrics', store=True)
    sales_per_click = fields.Float(string="Sales per Click", compute='_compute_metrics', store=True)

    def _get_click_domain(self):
        """Build domain for link tracker clicks based on dashboard filters"""
        self.ensure_one()
        domain = []

        if hasattr(self.env['link.tracker.click'], 'click_date'):
            domain += [
                ('click_date', '>=', self.date_from),
                ('click_date', '<=', self.date_to)
            ]
        else:
            domain += [
                ('create_date', '>=', self.date_from),
                ('create_date', '<=', self.date_to)
            ]

        if self.marketing_campaign_ids:
            domain.append(('campaign_id', 'in', self.marketing_campaign_ids.ids))

        if self.channel_ids:
            domain.append(('source_id', 'in', self.channel_ids.ids))
        if self.medium_ids:
            domain.append(('medium_id', 'in', self.medium_ids.ids))

        _logger.debug("Click domain: %s", domain)
        return domain

    def _get_sales_from_clicks(self, clicks):
        """
        Identify sales that originated from the provided clicks
        This uses UTM parameters to match clicks with sales

        :param clicks: recordset of link.tracker.click
        :return: recordset of sale.order
        """
        # First, check if we have mailing_trace_id on clicks (mass_mailing integration)
        if clicks and hasattr(clicks[0], 'mailing_trace_id'):
            trace_ids = clicks.mapped('mailing_trace_id')
            trace_ids = [tid for tid in trace_ids if tid]
            if trace_ids:
                sales = self.env['sale.order'].search([
                    ('date_order', '>=', self.date_from),
                    ('date_order', '<=', self.date_to),
                    ('state', 'in', ['sale', 'done']),
                    ('mailing_trace_ids', 'in', trace_ids),
                ])
                if sales:
                    return sales

        # Match based on UTM parameters
        # Get unique campaign, source, medium combinations from clicks
        utm_combinations = []

        for click in clicks:
            utm_combo = {
                'campaign_id': click.campaign_id.id if click.campaign_id else False,
                'source_id': click.link_id.source_id.id if hasattr(click.link_id,
                                                                   'source_id') and click.link_id.source_id else False,
                'medium_id': click.link_id.medium_id.id if hasattr(click.link_id,
                                                                   'medium_id') and click.link_id.medium_id else False
            }

            if utm_combo not in utm_combinations:
                utm_combinations.append(utm_combo)

        # Find sales that match these UTM combinations
        all_sales = self.env['sale.order']

        for combo in utm_combinations:
            domain = [
                ('date_order', '>=', self.date_from),
                ('date_order', '<=', self.date_to),
                ('state', 'in', ['sale', 'done']),
            ]

            if combo['campaign_id']:
                domain.append(('campaign_id', '=', combo['campaign_id']))
            if combo['source_id']:
                domain.append(('source_id', '=', combo['source_id']))
            if combo['medium_id']:
                domain.append(('medium_id', '=', combo['medium_id']))

            sales = self.env['sale.order'].search(domain)
            all_sales |= sales

        # Attempt direct matching if we have sale_id on link_tracker_click (custom field)
        if clicks and hasattr(clicks[0], 'sale_id'):
            sale_ids = clicks.mapped('sale_id').ids
            sale_ids = [sid for sid in sale_ids if sid]
            if sale_ids:
                direct_sales = self.env['sale.order'].browse(sale_ids).filtered(
                    lambda s: s.state in ['sale', 'done'] and
                              s.date_order.date() >= self.date_from and
                              s.date_order.date() <= self.date_to
                )
                all_sales |= direct_sales

        return all_sales

    def _calculate_avg_time_to_purchase(self, clicks, sales):
        """
        Calculate the average time between a click and a purchase

        :param clicks: recordset of link.tracker.click
        :param sales: recordset of sale.order
        :return: float (hours)
        """
        if not clicks or not sales:
            return 0.0

        # If we have mailing_trace_id on clicks and sales
        total_hours = 0
        count = 0

        if hasattr(clicks[0], 'mailing_trace_id') and hasattr(sales[0], 'mailing_trace_ids'):
            for sale in sales:
                traces = sale.mailing_trace_ids
                if not traces:
                    continue

                related_clicks = clicks.filtered(lambda c: c.mailing_trace_id and c.mailing_trace_id in traces.ids)
                for click in related_clicks:
                    click_time = click.create_date
                    order_time = sale.date_order
                    if click_time and order_time and click_time <= order_time:
                        delta = order_time - click_time
                        total_hours += delta.total_seconds() / 3600
                        count += 1

        # If we have sale_id on link_tracker_click
        elif hasattr(clicks[0], 'sale_id'):
            for click in clicks:
                if click.sale_id and click.sale_id in sales:
                    click_time = click.create_date
                    order_time = click.sale_id.date_order
                    if click_time and order_time and click_time <= order_time:
                        delta = order_time - click_time
                        total_hours += delta.total_seconds() / 3600
                        count += 1

        # Fall back to averages based on UTM matching
        else:
            # Group click times by UTM parameters
            utm_to_click_times = {}
            for click in clicks:
                key = (
                    click.campaign_id.id if click.campaign_id else False,
                    click.link_id.source_id.id if hasattr(click.link_id,
                                                          'source_id') and click.link_id.source_id else False,
                    click.link_id.medium_id.id if hasattr(click.link_id,
                                                          'medium_id') and click.link_id.medium_id else False,
                )
                if key not in utm_to_click_times:
                    utm_to_click_times[key] = []
                utm_to_click_times[key].append(click.create_date)

            # Match sales to earliest clicks with the same UTM
            for sale in sales:
                key = (
                    sale.campaign_id.id if sale.campaign_id else False,
                    sale.source_id.id if sale.source_id else False,
                    sale.medium_id.id if sale.medium_id else False,
                )

                if key in utm_to_click_times and utm_to_click_times[key]:
                    # Find earliest click that happened before the sale
                    valid_clicks = [c for c in utm_to_click_times[key] if c <= sale.date_order]
                    if valid_clicks:
                        earliest_click = min(valid_clicks)
                        delta = sale.date_order - earliest_click
                        total_hours += delta.total_seconds() / 3600
                        count += 1

        return total_hours / count if count else 0.0

    @api.depends('date_from', 'date_to', 'marketing_campaign_ids', 'channel_ids', 'medium_ids')
    def _compute_metrics(self):
        """Compute all dashboard metrics based on current filters"""
        for rec in self:
            print("Computing metrics for dashboard: %s", rec.name)
            clicks = self.env['link.tracker.click'].search(rec._get_click_domain())
            print("Total clicks found: %d", len(clicks))
            rec.total_clicks = len(clicks)
            # First identify sales that originated from clicks
            click_sourced_sales = rec._get_sales_from_clicks(clicks)

            # Then compute "normal" sales based on UTM parameters
            sales_domain = [
                ('date_order', '>=', rec.date_from),
                ('date_order', '<=', rec.date_to),
                ('state', 'in', ['sale', 'done'])
            ]

            if rec.marketing_campaign_ids:
                sales_domain.append(('campaign_id', 'in', rec.marketing_campaign_ids.ids))

            click_sourced_sales = clicks.mapped('sale_id')
            rec.total_sales = len(click_sourced_sales)
            print("total sales : ",)
            rec.total_revenue = sum(click_sourced_sales.mapped('amount_total'))
            clicks = self.env['link.tracker.click'].search(rec._get_click_domain())
            all_sales = self.env['sale.order'].search(sales_domain)
            print("Total sales found: %d", len(all_sales))


            rec.unique_clicks = len(set(clicks.mapped('ip'))) if clicks else 0

            # Click-sourced metrics
            rec.total_click_sourced_sales = len(click_sourced_sales)
            rec.sales_per_click = rec.total_click_sourced_sales / rec.total_clicks if rec.total_clicks else 0
            rec.avg_time_to_purchase = rec._calculate_avg_time_to_purchase(clicks, click_sourced_sales)

            # Calculated metrics
            rec.conversion_rate = (rec.total_click_sourced_sales / rec.total_clicks ) if rec.total_clicks else 0
            rec.avg_order_value = rec.total_revenue / rec.total_sales if rec.total_sales else 0

            # Additional metrics
            rec.bounce_rate = rec._calculate_bounce_rate(clicks)
            rec.cac = rec._calculate_cac(all_sales)
            rec.roi = rec._calculate_roi(rec.total_revenue, rec.cac)

            rec.last_refresh = fields.Datetime.now()

    @api.depends('total_clicks', 'unique_clicks', 'conversion_rate', 'total_sales', 'total_revenue', 'avg_order_value',
                 'prev_total_clicks', 'prev_unique_clicks', 'prev_conversion_rate', 'prev_total_sales',
                 'prev_total_revenue', 'prev_avg_order_value')
    def _compute_trends(self):
        """Compute trend percentages for all metrics"""
        for rec in self:
            rec.click_trend = self._calculate_percentage_change(rec.total_clicks, rec.prev_total_clicks)
            rec.unique_click_trend = self._calculate_percentage_change(rec.unique_clicks, rec.prev_unique_clicks)
            rec.conversion_trend = self._calculate_percentage_change(rec.conversion_rate, rec.prev_conversion_rate)
            rec.sales_trend = self._calculate_percentage_change(rec.total_sales, rec.prev_total_sales)
            rec.revenue_trend = self._calculate_percentage_change(rec.total_revenue, rec.prev_total_revenue)
            rec.aov_trend = self._calculate_percentage_change(rec.avg_order_value, rec.prev_avg_order_value)

    def _calculate_percentage_change(self, current, previous):
        if not previous:
            return 0.0
        return ((current - previous) / previous) * 100 if previous else 0.0

    @api.depends('date_from', 'date_to', 'marketing_campaign_ids', 'channel_ids', 'medium_ids', 'total_clicks',
                 'unique_clicks')
    def _compute_chart_data(self):
        """Compute data for dashboard charts"""
        for rec in self:
            print("Computing chart data for dashboard: %s", rec.name)
            daily_clicks = []
            current_date = rec.date_from
            clicks = self.env['link.tracker.click'].search(rec._get_click_domain())
            while current_date <= rec.date_to:
                day_domain = rec._get_click_domain()

                if hasattr(self.env['link.tracker.click'], 'click_date'):
                    day_domain = [d for d in day_domain if not ('click_date' in str(d))]
                    day_domain += [
                        ('click_date', '>=', current_date),
                        ('click_date', '<', current_date + timedelta(days=1))
                    ]
                else:
                    day_domain = [d for d in day_domain if not ('create_date' in str(d))]
                    day_domain += [
                        ('create_date', '>=', current_date),
                        ('create_date', '<', current_date + timedelta(days=1))
                    ]

                day_clicks = self.env['link.tracker.click'].search(day_domain)

                # Find the sales that came from these clicks
                day_click_sales = rec._get_sales_from_clicks(day_clicks)

                daily_clicks.append({
                    'date': current_date.strftime('%Y-%m-%d'),
                    'clicks': len(day_clicks),
                    'unique_clicks': len(set(day_clicks.mapped('ip'))) if day_clicks else 0,
                    'sales': len(day_click_sales),
                    'revenue': sum(day_click_sales.mapped('amount_total')) if day_click_sales else 0
                })
                current_date += timedelta(days=1)

            rec.daily_clicks_data = json.dumps(daily_clicks)
            print("Daily clicks data computed")

            channel_data = []
            if rec.channel_ids:
                for channel in rec.channel_ids:
                    channel_domain = rec._get_click_domain()

                    if hasattr(self.env['link.tracker.click'], 'source_id'):
                        channel_domain = [d for d in channel_domain if not ('source_id' in str(d))]
                        channel_domain.append(('source_id', '=', channel.id))
                    else:
                        # Try to find clicks with links that have this source
                        link_ids = self.env['link.tracker'].search([('source_id', '=', channel.id)]).ids
                        if link_ids:
                            channel_domain.append(('link_id', 'in', link_ids))

                    channel_clicks = self.env['link.tracker.click'].search(channel_domain)

                    # Find sales that came from these clicks
                    channel_click_sales = rec._get_sales_from_clicks(channel_clicks)

                    conversion = (len(channel_click_sales) / len(channel_clicks)) * 100 if channel_clicks else 0

                    channel_data.append({
                        'source': channel.name,
                        'clicks': len(channel_clicks),
                        'sales': len(channel_click_sales),
                        'revenue': sum(channel_click_sales.mapped('amount_total')) if channel_click_sales else 0,
                        'conversion_rate': round(conversion, 2)
                    })

            rec.channel_performance_data = json.dumps(channel_data)
            print("Channel performance data computed")

            campaign_data = []
            if rec.marketing_campaign_ids:
                for campaign in rec.marketing_campaign_ids:
                    # Find clicks for this campaign
                    campaign_clicks = clicks.filtered(lambda c: c.campaign_id and c.campaign_id.id == campaign.id)

                    # Find sales that came from these clicks
                    campaign_click_sales = rec._get_sales_from_clicks(campaign_clicks)

                    # Also find all sales with this campaign for comparison
                    sales_domain = [
                        ('date_order', '>=', rec.date_from),
                        ('date_order', '<=', rec.date_to),
                        ('state', 'in', ['sale', 'done']),
                        ('campaign_id', '=', campaign.id)
                    ]
                    all_campaign_sales = self.env['sale.order'].search(sales_domain)

                    campaign_data.append({
                        'campaign': campaign.name,
                        'clicks': len(campaign_clicks),
                        'tracked_sales': len(campaign_click_sales),
                        'tracked_revenue': sum(
                            campaign_click_sales.mapped('amount_total')) if campaign_click_sales else 0,
                        'total_sales': len(all_campaign_sales),
                        'total_revenue': sum(all_campaign_sales.mapped('amount_total')) if all_campaign_sales else 0
                    })

            rec.campaign_revenue_data = json.dumps(campaign_data)
            print("Campaign revenue data computed")

            medium_data = []
            if rec.medium_ids:
                for medium in rec.medium_ids:
                    medium_domain = rec._get_click_domain()

                    if hasattr(self.env['link.tracker.click'], 'medium_id'):
                        medium_domain = [d for d in medium_domain if not ('medium_id' in str(d))]
                        medium_domain.append(('medium_id', '=', medium.id))
                    else:
                        # Try to find clicks with links that have this medium
                        link_ids = self.env['link.tracker'].search([('medium_id', '=', medium.id)]).ids
                        if link_ids:
                            medium_domain.append(('link_id', 'in', link_ids))

                    medium_clicks = self.env['link.tracker.click'].search(medium_domain)

                    # Find sales that came from these clicks
                    medium_click_sales = rec._get_sales_from_clicks(medium_clicks)

                    conversion = (len(medium_click_sales) / len(medium_clicks) * 100) if medium_clicks else 0

                    medium_data.append({
                        'medium': medium.name,
                        'clicks': len(medium_clicks),
                        'sales': len(medium_click_sales),
                        'revenue': sum(medium_click_sales.mapped('amount_total')) if medium_click_sales else 0,
                        'conversion_rate': round(conversion, 2)
                    })

            rec.conversion_by_medium_data = json.dumps(medium_data)
            print("Conversion by medium data computed")

    def _calculate_bounce_rate(self, clicks):
        """
        Calculate bounce rate based on user behavior
        A bounce is defined as a session with only one page view and no conversion
        """
        if not clicks:
            return 0.0

        # Group clicks by IP to identify sessions
        sessions = {}
        for click in clicks:
            if click.ip:
                if click.ip not in sessions:
                    sessions[click.ip] = {
                        'clicks': [],
                        'converted': False
                    }
                sessions[click.ip]['clicks'].append(click.id)

                # Check if this click resulted in a sale
                if hasattr(click, 'sale_id') and click.sale_id:
                    sessions[click.ip]['converted'] = True

        # Count bounces (sessions with 1 click and no conversion)
        bounce_count = sum(
            1 for session in sessions.values() if len(session['clicks']) == 1 and not session['converted'])
        return (bounce_count / len(sessions)) * 100 if sessions else 0.0

    def _calculate_cac(self, sales):
        """
        Calculate Customer Acquisition Cost
        This would typically involve marketing costs which might be stored elsewhere
        For now, we'll use a simplified approach
        """
        if not sales:
            return 0.0

        # Try to find marketing costs from campaigns
        total_cost = 0.0
        if self.marketing_campaign_ids and hasattr(self.marketing_campaign_ids[0], 'cost'):
            for campaign in self.marketing_campaign_ids:
                total_cost += campaign.cost if hasattr(campaign, 'cost') else 0.0

            # If no costs are found, use a placeholder value
            if total_cost == 0.0:
                return 25.0  # Placeholder value

            new_customers = len(set(sales.mapped('partner_id.id')))
            return total_cost / new_customers if new_customers else 0.0
        else:
            # If no campaign costs are available, use a placeholder
            return 25.0

    def _calculate_roi(self, total_revenue, cac):
        """Calculate Return on Investment based on revenue and acquisition cost"""
        total_cost = cac * (self.total_sales or 1)
        if not total_cost:
            return 0.0
        return ((total_revenue - total_cost) / total_cost) * 100 if total_cost else 0.0

    def action_refresh(self):
        self.ensure_one()
        self._compute_metrics()
        self._compute_chart_data()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_view_clicks(self):
        self.ensure_one()
        return {
            'name': 'Clicks Analysis',
            'type': 'ir.actions.act_window',
            'res_model': 'link.tracker.click',
            'view_mode': 'tree,pivot,graph',
            'domain': self._get_click_domain(),
            'context': {'create': False}
        }

    def action_view_click_sourced_sales(self):
        """View only sales that originated from tracked clicks"""
        self.ensure_one()
        clicks = self.env['link.tracker.click'].search(self._get_click_domain())
        sales = self._get_sales_from_clicks(clicks)

        return {
            'name': 'Click-Sourced Sales',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,pivot,graph',
            'domain': [('id', 'in', sales.ids)],
            'context': {'create': False}
        }

    def action_view_sales(self):
        self.ensure_one()
        sales_domain = [
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('state', 'in', ['sale', 'done'])
        ]

        if self.marketing_campaign_ids:
            sales_domain.append(('campaign_id', 'in', self.marketing_campaign_ids.ids))
        if self.channel_ids:
            sales_domain.append(('source_id', 'in', self.channel_ids.ids))
        if self.medium_ids:
            sales_domain.append(('medium_id', 'in', self.medium_ids.ids))

        return {
            'name': 'Sales Analysis',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,pivot,graph',
            'domain': sales_domain,
            'context': {'create': False}
        }

    def action_compare_periods(self):
        self.ensure_one()

        current_period_days = (self.date_to - self.date_from).days + 1
        previous_period_end = self.date_from - timedelta(days=1)
        previous_period_start = previous_period_end - timedelta(days=current_period_days - 1)

        self.write({
            'comparison_date_from': previous_period_start,
            'comparison_date_to': previous_period_end
        })

        prev_click_domain = self._get_click_domain()

        if hasattr(self.env['link.tracker.click'], 'click_date'):
            prev_click_domain = [d for d in prev_click_domain if not ('click_date' in str(d))]
            prev_click_domain += [
                ('click_date', '>=', previous_period_start),
                ('click_date', '<=', previous_period_end)
            ]
        else:
            prev_click_domain = [d for d in prev_click_domain if not ('create_date' in str(d))]
            prev_click_domain += [
                ('create_date', '>=', previous_period_start),
                ('create_date', '<=', previous_period_end)
            ]

        prev_clicks = self.env['link.tracker.click'].search(prev_click_domain)

        prev_sales_domain = [
            ('date_order', '>=', previous_period_start),
            ('date_order', '<=', previous_period_end),
            ('state', 'in', ['sale', 'done'])
        ]

        if self.marketing_campaign_ids:
            prev_sales_domain.append(('campaign_id', 'in', self.marketing_campaign_ids.ids))
        if self.channel_ids:
            prev_sales_domain.append(('source_id', 'in', self.channel_ids.ids))
        if self.medium_ids:
            prev_sales_domain.append(('medium_id', 'in', self.medium_ids.ids))

        prev_sales = self.env['sale.order'].search(prev_sales_domain)

        prev_total_clicks = len(prev_clicks)
        prev_unique_clicks = len(set(prev_clicks.mapped('ip'))) if prev_clicks else 0
        prev_total_sales = len(prev_sales)
        prev_total_revenue = sum(prev_sales.mapped('amount_total'))
        prev_conversion_rate = (prev_total_sales / prev_total_clicks * 100) if prev_total_clicks else 0
        prev_avg_order_value = prev_total_revenue / prev_total_sales if prev_total_sales else 0

        self.write({
            'prev_total_clicks': prev_total_clicks,
            'prev_unique_clicks': prev_unique_clicks,
            'prev_conversion_rate': prev_conversion_rate,
            'prev_total_sales': prev_total_sales,
            'prev_total_revenue': prev_total_revenue,
            'prev_avg_order_value': prev_avg_order_value
        })

        self._compute_trends()

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_clear_comparison(self):
        self.ensure_one()
        self.write({
            'comparison_date_from': False,
            'comparison_date_to': False,
            'prev_total_clicks': 0,
            'prev_unique_clicks': 0,
            'prev_conversion_rate': 0,
            'prev_total_sales': 0,
            'prev_total_revenue': 0,
            'prev_avg_order_value': 0
        })

        self._compute_trends()

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def _cron_refresh_dashboards(self):
        dashboards = self.search([('active', '=', True)])
        for dashboard in dashboards:
            dashboard.action_refresh()