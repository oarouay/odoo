from odoo import models, api


class MarketingCampaignCostReport(models.AbstractModel):
    _name = 'report.ai_mailing.campaign_cost_report'  # Match the report_name from XML
    _description = 'Marketing Campaign Cost Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Get the campaign
        campaign = self.env['marketing.campaign'].browse(docids)

        # Get all costs for this campaign
        costs = self.env['marketing.campaign.cost'].search([
            ('campaign_id', 'in', docids)
        ], order='date asc')

        # Prepare cost_by_type data structure
        cost_by_type = {}
        for cost in costs:
            cost_type = dict(cost._fields['cost_type'].selection).get(cost.cost_type)
            if cost_type not in cost_by_type:
                cost_by_type[cost_type] = []
            cost_by_type[cost_type].append({
                'date': cost.date,
                'name': cost.name,
                'amount': cost.amount,
                'notes': cost.notes or ''
            })

        return {
            'doc_ids': docids,
            'doc_model': 'marketing.campaign',
            'docs': campaign,
            'costs': costs,
            'cost_by_type': cost_by_type or None,  # Pass None if empty
            'total': sum(cost.amount for cost in costs),
            'has_costs': bool(costs)  # Helper flag for template
        }