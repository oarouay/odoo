# 1. Python Model Method (marketing_campaign.py)
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
import html
import re

_logger = logging.getLogger(__name__)


class MarketingCampaign(models.Model):
    _inherit = 'marketing.campaign'

    ai_dashboard_report = fields.Html('AI Dashboard Report', sanitize=False)
    ai_report_generation_date = fields.Datetime('Report Generation Date')

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
        comparison_campaign = self.browse(comparison_campaign_id) if comparison_campaign_id else False

        # Debug log
        _logger.info(f"Generating report for campaign ID: {campaigns.ids}, comparison ID: {comparison_campaign_id}")

        # 1. Get metrics (handles both single and comparison cases)
        try:
            metrics = self.get_dashboard_metrics(domain=domain, comparison_campaign_id=comparison_campaign_id)
            _logger.info(f"Metrics fetched successfully")
        except Exception as e:
            error_msg = f"<h2>Error</h2><p>Could not fetch dashboard metrics: {e}</p>"
            _logger.error(f"Error fetching metrics: {e}")
            self._store_ai_report(campaigns, error_msg)
            return error_msg

        # 2. Prepare the prompt for Gemini
        metrics_json = json.dumps(metrics, indent=2)
        prompt_base = (
            "You are an expert marketing analyst interpreting marketing campaign data for a non-technical user. "
            "Format your response as a visually appealing HTML report using simple language. Use headings (h3), paragraphs (p), and lists (ul/li) for clarity. "
            f"Primary campaign name: {campaigns.name}. "
            "Focus on the most important metrics like Clicks, Sales, Revenue, Conversion Rate, Cost, and ROI.\n\n"
            "Here are the metrics data (JSON):\n"
            f"{metrics_json}\n\n"
            "IMPORTANT: Format your response as valid HTML that can be rendered in a PDF report. "
            "Do not include DOCTYPE, html, head or body tags - just the content elements. "
            "Use only basic HTML elements that render well in PDF: h2, h3, p, ul, li, table, tr, td, strong, em."
        )

        if comparison_campaign_id and any(key.endswith('_change_percent') for key in metrics):
            # Comparison case
            prompt = (
                    prompt_base +
                    f"Comparison campaign name: {comparison_campaign.name}. "
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
        google_api_key = config.get_param('GOOGLE_API_KEY')  # Use a specific key name

        if not google_api_key:
            html_report = ("<h2>Configuration Error</h2>"
                           "<p>The Google Gemini API Key is not configured in Odoo's System Parameters. "
                           "Please ask your administrator to add a parameter with the key 'GOOGLE_API_KEY'.</p>")

            self._store_ai_report(campaigns, html_report)
            return html_report

        # 4. Configure Gemini and generate content
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')  # Or your preferred model

            _logger.info("Sending request to Gemini API")
            gemini_response = model.generate_content(prompt)
            _logger.info("Received response from Gemini API")

            # Basic check if response has text
            if hasattr(gemini_response, 'text') and gemini_response.text:
                html_report = gemini_response.text

                # Basic sanitization to ensure only allowed HTML tags are used
                html_report = self._sanitize_html_for_pdf(html_report)

                _logger.info("Generated HTML report successfully")
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

                _logger.warning(f"AI generation issue: {html_report}")

        except ImportError:
            error_msg = _(
                "The required Python library 'google-generativeai' is not installed. Please contact your administrator.")
            _logger.error(error_msg)
            raise UserError(error_msg)
        except Exception as e:
            html_report = (
                "<h2>AI Report Generation Failed</h2>"
                f"<p>Could not generate the report due to an API error: {str(e)}</p>"
                "<p>Please check the Odoo server logs for more details and ensure the API key is valid.</p>"
            )
            _logger.error(f"Error generating AI report: {str(e)}")

        # Store the report in the database
        self._store_ai_report(campaigns, html_report)
        return html_report

    def _sanitize_html_for_pdf(self, html_content):
        """
        Sanitize HTML to ensure it's PDF-friendly

        :param html_content: Raw HTML content from Gemini
        :return: Sanitized HTML content
        """
        # Remove any script tags and their contents
        html_content = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html_content)

        # Remove any style tags and their contents
        html_content = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', html_content)

        # Remove DOCTYPE, html, head, body tags if they exist
        html_content = re.sub(r'<!DOCTYPE[^>]*>', '', html_content)
        html_content = re.sub(r'<html[^>]*>|<\/html>', '', html_content)
        html_content = re.sub(r'<head[^>]*>.*?<\/head>', '', html_content)
        html_content = re.sub(r'<body[^>]*>|<\/body>', '', html_content)

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
        now = fields.Datetime.now()
        for campaign in campaigns:
            campaign.write({
                'ai_dashboard_report': html_report,
                'ai_report_generation_date': now
            })

        _logger.info(f"AI report stored for campaigns: {campaigns.ids}")