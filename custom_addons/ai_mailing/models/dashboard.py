import google.generativeai as genai
from odoo.exceptions import UserError
from odoo import models, api, fields, _
from datetime import datetime, timedelta
import json
import re

class MarketingCampaignClicksOverTime(models.Model):
    _inherit = "marketing.campaign"

    ai_dashboard_report = fields.Html(string="AI Dashboard Report", readonly=True,
                                      help="AI-generated analysis of campaign performance")
    ai_report_generation_date = fields.Datetime(string="Report Generation Date", readonly=True)


    def calculate_campaign_metrics(self, campaigns):
        """
        Calculate key metrics for the given campaigns

        :param campaigns: recordset of marketing.campaign records
        :return: dict containing all calculated metrics
        """
        # Get all clicks related to the campaigns
        clicks = self.env['link.tracker.click'].search([
            ('link_id.campaign_id1', 'in', campaigns.ids)
        ])

        # Get all sales sourced from these clicks
        click_sourced_sales = clicks.mapped('sale_id')

        # Calculate base metrics
        total_clicks = len(clicks)
        unique_clicks = len(set(clicks.mapped('ip')))
        total_sales = len(click_sourced_sales)
        total_revenue = sum(click_sourced_sales.mapped('amount_total'))
        total_cost = sum(campaigns.mapped('cost'))

        # Calculate conversion rate and average order value
        conversion_rate = (total_sales / total_clicks * 100) if total_clicks else 0
        avg_order = (total_revenue / total_sales) if total_sales else 0

        # Calculate financial KPIs
        roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost else 0
        cpc = (total_cost / total_clicks) if total_clicks else 0
        cpa = (total_cost / total_sales) if total_sales else 0

        return {
            'total_clicks': total_clicks,
            'unique_clicks': unique_clicks,
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'conversion_rate': conversion_rate,
            'avg_order': avg_order,
            'roi': roi,
            'cpc': cpc,
            'cpa': cpa
        }

    @api.model
    def get_dashboard_metrics(self, domain=None, comparison_campaign_id=None):
        """
        Compute dashboard metrics for campaigns matching the given domain.
        If no domain is provided, computes metrics for all campaigns.
        Optionally compares results with another campaign.

        :param domain: Optional domain to filter campaigns
        :param comparison_campaign_id: Optional campaign ID to compare against
        :return: Dictionary with computed metrics and optional comparison percentages
        """
        # Set default domain if none is provided
        if domain is None:
            domain = []

        # Search for primary campaigns
        campaigns = self.search(domain)
        primary_results = self.calculate_campaign_metrics(campaigns)

        # Set defaults in case there's no comparison
        comparison_results = {}
        comparison_metrics = {}

        if comparison_campaign_id:
            comparison_campaign = self.search([('id', '=', comparison_campaign_id)])
            comparison_results = self.calculate_campaign_metrics(comparison_campaign)

            # Calculate percentage differences safely
            def percentage_change(primary, comparison):
                if comparison == 0:
                    return 0.0
                return round(((primary - comparison) / comparison) * 100, 2)

            comparison_metrics = {
                'clicks_change_percent': percentage_change(primary_results['total_clicks'],
                                                           comparison_results['total_clicks']),
                'unique_clicks_change_percent': percentage_change(primary_results['unique_clicks'],
                                                                  comparison_results['unique_clicks']),
                'sales_change_percent': percentage_change(primary_results['total_sales'],
                                                          comparison_results['total_sales']),
                'revenue_change_percent': percentage_change(primary_results['total_revenue'],
                                                            comparison_results['total_revenue']),
                'conversion_rate_change_percent': percentage_change(primary_results['conversion_rate'],
                                                                    comparison_results['conversion_rate']),
                'avg_order_change_percent': percentage_change(primary_results['avg_order'],
                                                              comparison_results['avg_order']),
                'cost_change_percent': percentage_change(primary_results['total_cost'],
                                                         comparison_results['total_cost']),
                'roi_change_percent': percentage_change(primary_results['roi'], comparison_results['roi']),
                'cpc_change_percent': percentage_change(primary_results['cpc'], comparison_results['cpc']),
                'cpa_change_percent': percentage_change(primary_results['cpa'], comparison_results['cpa']),
            }

        return {
            'total_clicks': primary_results['total_clicks'],
            'unique_clicks': primary_results['unique_clicks'],
            'total_sales': primary_results['total_sales'],
            'total_revenue': round(primary_results['total_revenue'], 2),
            'conversion_rate': round(primary_results['conversion_rate'], 2),
            'avg_order': round(primary_results['avg_order'], 2),
            'total_cost': round(primary_results['total_cost'], 2),
            'roi': round(primary_results['roi'], 2),
            'cpc': round(primary_results['cpc'], 2),
            'cpa': round(primary_results['cpa'], 2),
            **comparison_metrics  # Include comparison data if available
        }


    @api.model
    def get_default_chart_data(self, domain=None):
        """Default chart data if no specific method is available"""
        return {
            'labels': ['No Data Available'],
            'datasets': [{
                'label': 'No Data',
                'data': [100],
                'backgroundColor': ['#cccccc']
            }]
        }

    @api.model
    def get_top_products_data(self, domain=None):
        """Get data for top products chart"""
        if domain is None:
            domain = []

        # Find campaigns matching the domain
        campaigns = self.search(domain)

        # Get all tracked links for these campaigns
        link_ids = self.env['link.tracker'].search([('campaign_id1', 'in', campaigns.ids)])
        clicks = self.env['link.tracker.click'].search([('link_id', 'in', link_ids.ids)])

        # Get sales from these clicks
        sales = self.env['sale.order'].search([('id', 'in', clicks.mapped('sale_id').ids)])

        # Get order lines from these sales
        order_lines = self.env['sale.order.line'].search([
            ('order_id', 'in', sales.ids),
            ('product_id.type', '!=', 'service')  # This filters out service products like delivery
        ])

        # Group by product and sum quantities
        product_data = {}
        for line in order_lines:
            product_name = line.product_id.name
            if product_name in product_data:
                product_data[product_name] += line.product_uom_qty
            else:
                product_data[product_name] = line.product_uom_qty

        # Sort by quantity and take top 5
        sorted_products = sorted(product_data.items(), key=lambda x: x[1], reverse=True)[:5]

        # If no data, return default
        if not sorted_products:
            return self.get_default_chart_data()

        # Prepare chart data
        labels = [product[0] for product in sorted_products]
        data = [product[1] for product in sorted_products]

        # Generate colors
        colors = [
            '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b',
            '#5a5c69', '#858796', '#6610f2', '#fd7e14', '#20c9a6'
        ]

        return {
            'labels': labels,
            'datasets': [{
                'label': 'Units Sold',
                'data': data,
                'backgroundColor': colors[:len(labels)],
                'hoverOffset': 4
            }]
        }

    @api.model
    def get_clicks_and_sales_over_time(self, domain=None, interval='day', date_range=30):
        """
        Get clicks and sales data over time for charting.

        :param domain: Optional domain to filter campaigns
        :param interval: Time interval for grouping ('day', 'week', 'month')
        :param date_range: Number of days to look back
        :return: Dictionary with labels and datasets for the chart
        """
        if domain is None:
            domain = []

        # Find campaigns matching the domain
        campaigns = self.search(domain)

        if not campaigns:
            return {
                'labels': [],
                'datasets': [
                    {
                        'label': 'Clicks',
                        'data': [],
                    },
                    {
                        'label': 'Sales',
                        'data': [],
                    }
                ]
            }

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=date_range)

        # Format for database query based on interval
        if interval == 'day':
            date_format = 'YYYY-MM-DD'
            interval_sql = 'day'
        elif interval == 'week':
            date_format = 'IYYY-IW'  # ISO year and week
            interval_sql = 'week'
        elif interval == 'month':
            date_format = 'YYYY-MM'
            interval_sql = 'month'
        else:
            date_format = 'YYYY-MM-DD'
            interval_sql = 'day'

        # Get all tracked links for these campaigns
        link_ids = self.env['link.tracker'].search([('campaign_id1', 'in', campaigns.ids)])

        if not link_ids:
            return {
                'labels': [],
                'datasets': [
                    {
                        'label': 'Clicks',
                        'data': [],
                    },
                    {
                        'label': 'Sales',
                        'data': [],
                    }
                ]
            }

        # Query to get clicks grouped by date interval
        self.env.cr.execute(f"""
            SELECT 
                TO_CHAR(DATE_TRUNC('{interval_sql}', create_date), '{date_format}') as time_period,
                COUNT(*) as click_count
            FROM 
                link_tracker_click
            WHERE 
                link_id IN %s
                AND create_date >= %s
                AND create_date <= %s
            GROUP BY 
                time_period
            ORDER BY 
                time_period
        """, (tuple(link_ids.ids), start_date, end_date))

        click_results = self.env.cr.dictfetchall()

        # Create a dictionary for clicks by time period
        clicks_by_period = {r['time_period']: r['click_count'] for r in click_results}

        # Query to get sales grouped by date interval
        self.env.cr.execute(f"""
            SELECT 
                TO_CHAR(DATE_TRUNC('{interval_sql}', s.date_order), '{date_format}') as time_period,
                COUNT(DISTINCT s.id) as sale_count
            FROM 
                sale_order s
            JOIN 
                link_tracker_click ltc ON s.id = ltc.sale_id
            WHERE 
                ltc.link_id IN %s
                AND s.date_order >= %s
                AND s.date_order <= %s
            GROUP BY 
                time_period
            ORDER BY 
                time_period
        """, (tuple(link_ids.ids), start_date, end_date))

        sale_results = self.env.cr.dictfetchall()

        # Create a dictionary for sales by time period
        sales_by_period = {r['time_period']: r['sale_count'] for r in sale_results}

        # Combine all time periods from both queries
        all_periods = sorted(set(list(clicks_by_period.keys()) + list(sales_by_period.keys())))

        # Prepare data for chart
        click_data = [clicks_by_period.get(period, 0) for period in all_periods]
        sale_data = [sales_by_period.get(period, 0) for period in all_periods]

        return {
            'labels': all_periods,
            'datasets': [
                {
                    'label': 'Clicks',
                    'data': click_data,
                    'borderColor': 'rgb(75, 192, 192)',
                    'tension': 0.1
                },
                {
                    'label': 'Sales',
                    'data': sale_data,
                    'borderColor': 'rgb(255, 99, 132)',
                    'tension': 0.1
                }
            ]
        }

    @api.model
    def get_clicks_sales_by_source(self, domain=None, date_range=30):
        """
        Get clicks and sales data grouped by source_id with proper UTM source names.

        :param domain: Optional domain to filter campaigns
        :param date_range: Number of days to look back (default: 30)
        :return: Dictionary with source data including clicks and conversions
        """
        print("function works as expected")
        if domain is None:
            domain = []

        # Find campaigns matching the domain
        campaigns = self.search(domain)

        if not campaigns:
            return {
                'labels': [],
                'datasets': [
                    {
                        'label': 'Clicks',
                        'data': [],
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'borderColor': 'rgb(75, 192, 192)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Conversions',
                        'data': [],
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'borderColor': 'rgb(255, 99, 132)',
                        'borderWidth': 1
                    }
                ]
            }

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(date_range))

        # Get all tracked links for these campaigns
        link_ids = self.env['link.tracker'].search([('campaign_id1', 'in', campaigns.ids)])

        if not link_ids:
            return {
                'labels': [],
                'datasets': [
                    {
                        'label': 'Clicks',
                        'data': [],
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'borderColor': 'rgb(75, 192, 192)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Conversions',
                        'data': [],
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'borderColor': 'rgb(255, 99, 132)',
                        'borderWidth': 1
                    }
                ]
            }

        # Query to get clicks and conversions grouped by source_id
        # Join with utm_source to get the source names
        self.env.cr.execute("""
            SELECT 
                COALESCE(utm.name, 'Unknown') as source_name,
                lt.source_id,
                COUNT(ltc.id) as click_count,
                SUM(CASE WHEN ltc.converted THEN 1 ELSE 0 END) as conversion_count
            FROM 
                link_tracker_click ltc
            JOIN 
                link_tracker lt ON ltc.link_id = lt.id
            LEFT JOIN 
                utm_source utm ON lt.source_id = utm.id
            WHERE 
                ltc.link_id IN %s
                AND ltc.create_date >= %s
                AND ltc.create_date <= %s
            GROUP BY 
                utm.name, lt.source_id
            ORDER BY 
                click_count DESC
        """, (tuple(link_ids.ids), start_date, end_date))

        results = self.env.cr.dictfetchall()

        # If no results, return empty data
        if not results:
            return {
                'labels': [],
                'datasets': [
                    {
                        'label': 'Clicks',
                        'data': [],
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'borderColor': 'rgb(75, 192, 192)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Conversions',
                        'data': [],
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'borderColor': 'rgb(255, 99, 132)',
                        'borderWidth': 1
                    }
                ]
            }

        # Prepare data for chart
        source_names = [r['source_name'] for r in results]
        click_counts = [r['click_count'] for r in results]
        conversion_counts = [r['conversion_count'] for r in results]

        # Calculate conversion rates for the table data
        table_data = []
        for i, result in enumerate(results):
            source_name = result['source_name']
            source_id = result['source_id']
            clicks = click_counts[i]
            conversions = conversion_counts[i]
            conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0

            table_data.append({
                'source_name': source_name,
                'source_id': source_id,
                'clicks': clicks,
                'conversions': conversions,
                'conversion_rate': round(conversion_rate, 2)
            })

        # Prepare chart data
        return {
            'chart_data': {
                'labels': source_names,
                'datasets': [
                    {
                        'label': 'Clicks',
                        'data': click_counts,
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'borderColor': 'rgb(75, 192, 192)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Conversions',
                        'data': conversion_counts,
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'borderColor': 'rgb(255, 99, 132)',
                        'borderWidth': 1
                    }
                ]
            },
            'table_data': table_data
        }

    @api.model
    def get_campaign_roi_comparison_data(self, domain=None, date_range=30):
        """
        Get ROI comparison data across different campaigns.

        :param domain: Optional domain to filter campaigns
        :param date_range: Number of days to look back (default: 30)
        :return: Dictionary with chart data for Campaign ROI Comparison
        """
        if domain is None:
            domain = []

        # Add date range filter
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(date_range))
        domain += [('create_date', '>=', start_date), ('create_date', '<=', end_date)]

        # Search campaigns
        campaigns = self.search(domain)

        if not campaigns:
            return self.get_default_chart_data()

        # Get all tracked links for these campaigns
        link_ids = self.env['link.tracker'].search([('campaign_id1', 'in', campaigns.ids)])

        if not link_ids:
            return self.get_default_chart_data()

        # Query budget, revenue per campaign
        self.env.cr.execute("""
            SELECT 
                mc.name AS campaign_name,
                SUM(mc.cost) AS budget,
                SUM(so.amount_total) AS revenue
            FROM 
                marketing_campaign mc
            LEFT JOIN 
                link_tracker lt ON lt.campaign_id1 = mc.id
            LEFT JOIN 
                link_tracker_click ltc ON ltc.link_id = lt.id
            LEFT JOIN 
                sale_order so ON ltc.sale_id = so.id
            WHERE 
                mc.id IN %s
            GROUP BY 
                mc.name
            ORDER BY 
                revenue DESC
        """, (tuple(campaigns.ids),))

        results = self.env.cr.dictfetchall()

        if not results:
            return self.get_default_chart_data()

        # Calculate ROI for each campaign
        campaign_names = []
        roi_data = []
        table_data = []

        for result in results:
            campaign_name = result['campaign_name'] or 'Unknown'
            budget = result['budget'] or 0
            revenue = result['revenue'] or 0

            if budget:
                roi = ((revenue - budget) / budget) * 100
            else:
                roi = 0

            campaign_names.append(campaign_name)
            roi_data.append(round(roi, 2))

            table_data.append({
                'campaign_name': campaign_name,
                'budget': round(budget, 2),
                'revenue': round(revenue, 2),
                'roi': round(roi, 2)
            })

        # Sort by ROI descending
        combined = list(zip(campaign_names, roi_data, table_data))
        combined.sort(key=lambda x: x[1], reverse=True)

        campaign_names = [x[0] for x in combined]
        roi_data = [x[1] for x in combined]
        table_data = [x[2] for x in combined]

        # Limit to top 10 campaigns for visualization
        campaign_names = campaign_names[:10]
        roi_data = roi_data[:10]
        table_data = table_data[:10]

        return {
            'chart_data': {
                'labels': campaign_names,
                'datasets': [
                    {
                        'label': 'ROI (%)',
                        'data': roi_data,
                        'backgroundColor': 'rgba(75, 192, 192, 0.7)',
                        'borderColor': 'rgb(75, 192, 192)',
                        'borderWidth': 1,
                        'indexAxis': 'y',  # Make it horizontal bar
                    }
                ]
            },
            'table_data': table_data
        }

    @api.model
    def generate_gemini_dashboard_report(self, domain=None, comparison_campaign_id=None):
        """
        Generate an HTML report using Gemini that explains the dashboard metrics in simple terms
        and provides actionable suggestions. If a comparison campaign is selected, compare them.

        :param domain: Optional domain to filter primary campaigns
        :param comparison_campaign_id: Optional campaign ID to compare against
        :return: HTML string with the report
        """
        campaigns = self.search(domain)
        comparison_campaign = self.search([('id', '=', comparison_campaign_id)])
        # 1. Get metrics (handles both single and comparison cases)
        try:
            metrics = self.get_dashboard_metrics(domain=domain, comparison_campaign_id=comparison_campaign_id)
        except Exception as e:
            return f"<h2>Error</h2><p>Could not fetch dashboard metrics: {e}</p>"

        # 2. Prepare the prompt for Gemini
        metrics_json = json.dumps(metrics, indent=2)
        prompt_base = (
            "You are an expert marketing analyst interpreting marketing campaign data for a non-technical user. "
            "Format your response as a visually appealing HTML report that will be rendered in a PDF. "
            f"Primary campaign name: {campaigns.name}. "
            "Focus on the most important metrics like Clicks, Sales, Revenue, Conversion Rate, Cost, and ROI.\n\n"
            "Here are the metrics data (JSON):\n"
            f"{metrics_json}\n\n"
            "VERY IMPORTANT FORMATTING INSTRUCTIONS: \n"
            "1. Do NOT use markdown code blocks (```html) in your response, just provide clean HTML\n"
            "2. Use proper HTML tables with <table>, <tr>, <th>, and <td> tags\n"
            "3. Add Bootstrap-compatible classes to tables: class='table table-bordered table-striped'\n"
            "4. Use <strong> instead of <b> and <em> instead of <i>\n"
            "5. Keep styling minimal and compatible with PDF rendering\n"
            "6. Do not include DOCTYPE, html, head or body tags\n"
            "7. Use only basic HTML elements that render well in PDF: h1, h2, h3, p, ul, li, table, tr, td, strong, em\n"
            "8. Make the content visually readable with appropriate spacing and formatting"
        )

        if comparison_campaign_id and any(key.endswith('_change_percent') for key in metrics):
            # Comparison case
            prompt = (
                    prompt_base +
                    f"camparaison campaign name : {comparison_campaign.name}"
                    "Explain the key metrics for the primary campaign(s). "
                    "Then, analyze the comparison data (percentage changes). Highlight significant differences (positive or negative) between the primary selection and the comparison campaign. "
                    "Finally, provide 2-3 actionable recommendations based *specifically* on the comparison insights (e.g., if ROI decreased, suggest investigating cost or conversion issues). "
                    "Structure the HTML report with sections: 'Key Metrics Explained', 'Campaign Comparison', and 'Recommendations'."
            )
        else:
            # Single campaign case
            prompt = (
                    prompt_base +
                    "Explain the key metrics provided in the JSON data. "
                    "Then, based *only* on these numbers, provide 2-3 actionable recommendations to improve campaign performance (e.g., if conversion rate is low, suggest A/B testing calls to action). "
                    "Structure the HTML report with sections: 'Key Metrics Explained' and 'Recommendations'."
            )


        # 3. Get API Key from Odoo parameters
        config = self.env['ir.config_parameter'].sudo()
        google_api_key = config.get_param('GOOGLE_API_KEY') # Use a specific key name

        if not google_api_key:
            html_report = ("<h2>Configuration Error</h2>"
                           "<p>The Google Gemini API Key is not configured in Odoo's System Parameters. "
                           "Please ask your administrator to add a parameter with the key '<code>google.gemini.api.key</code>'.</p>")

            self._store_ai_report(campaigns, html_report)
        # 4. Configure Gemini and generate content
        try:
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')  # Or your preferred model
            gemini_response = model.generate_content(prompt)

            # Basic check if response has text
            if hasattr(gemini_response, 'text') and gemini_response.text:
                html_report = gemini_response.text
                # Optional: Basic sanitization or validation could be added here
                # For now, we assume Gemini returns safe HTML as requested.
            else:
                # Check for blocked prompts
                if hasattr(gemini_response, 'prompt_feedback') and gemini_response.prompt_feedback.block_reason:
                    block_reason = gemini_response.prompt_feedback.block_reason
                    html_report = (f"<h2>AI Report Generation Blocked</h2>"
                                   f"<p>The request was blocked by the AI's safety filters. Reason: {block_reason}</p>"
                                   f"<p>Please review the campaign data or try adjusting the request.</p>")
                else:
                    html_report = ("<h2>AI Report Generation Failed</h2>"
                                   "<p>The AI model returned an empty response. Please try again later.</p>")

        except ImportError:
            raise UserError(
                _("The required Python library 'google-generativeai' is not installed. Please contact your administrator."))
        except Exception as e:
            html_report = (
                "<h2>AI Report Generation Failed</h2>"
                f"<p>Could not generate the report due to an API error: {e}</p>"
                "<p>Please check the Odoo server logs for more details and ensure the API key is valid.</p>"
            )
        print(html_report)
        self._store_ai_report(campaigns, html_report)

    def _sanitize_html_for_pdf(self, html_content):
        """
        Sanitize HTML to ensure it's PDF-friendly

        :param html_content: Raw HTML content from Gemini
        :return: Sanitized HTML content
        """
        # Remove markdown code blocks (triple backticks)
        html_content = re.sub(r'```html\s*', '', html_content)
        html_content = re.sub(r'```\s*', '', html_content)

        # Remove any script tags and their contents
        html_content = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html_content)

        # Remove any style tags and their contents
        html_content = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', html_content)

        # Remove DOCTYPE, html, head, body tags if they exist
        html_content = re.sub(r'<!DOCTYPE[^>]*>', '', html_content)
        html_content = re.sub(r'<html[^>]*>|<\/html>', '', html_content)
        html_content = re.sub(r'<head[^>]*>.*?<\/head>', '', html_content)
        html_content = re.sub(r'<body[^>]*>|<\/body>', '', html_content)

        # Clean up any other markdown artifacts that might interfere with HTML rendering
        html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_content)  # Bold text
        html_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_content)  # Italic text

        # Wrap the content in a div with some basic styling
        html_content = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            {html_content}
        </div>
        """

        return html_content

    def _store_ai_report(self, campaigns, html_report):
        """
        Store the AI-generated report in the campaign record(s)

        :param campaigns: recordset of marketing.campaign records
        :param html_report: HTML string with the report content
        """
        clean_html_report=self._sanitize_html_for_pdf(html_report)
        now = fields.Datetime.now()
        campaigns.write({
            'ai_dashboard_report': clean_html_report,
            'ai_report_generation_date': now
        })

