from odoo import models, fields, api


class SocialFacebook(models.Model):
    _name = "social.facebook"
    _description = "Facebook Post"

    campaign_id = fields.Many2one('marketing.campaign', string="Campaign", required=True, ondelete='cascade')
    name = fields.Char(string="Headline", required=True)
    publish_date = fields.Datetime(string="Publish Date")
    content = fields.Text(string="Post Content")
    media_suggestion = fields.Text(string="Media Suggestion")

    # New fields for Facebook scheduling
    scheduled_fb_post_id = fields.Char(string="Facebook Post ID", help="ID of the scheduled post on Facebook")
    fb_scheduling_status = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled on Facebook'),
        ('published', 'Published'),
        ('failed', 'Scheduling Failed')
    ], string="Scheduling Status", default='draft')

    # You might want to add methods to check post status or cancel scheduled posts
    def action_check_post_status(self):
        """Check the status of the scheduled post on Facebook."""
        for record in self:
            if record.scheduled_fb_post_id and record.campaign_id.fb_access_token:
                try:
                    import requests
                    url = f"https://graph.facebook.com/v17.0/{record.scheduled_fb_post_id}"
                    params = {'access_token': record.campaign_id.fb_access_token}
                    response = requests.get(url, params=params)
                    data = response.json()

                    if 'is_published' in data and data['is_published']:
                        record.write({'fb_scheduling_status': 'published'})

                    return {'type': 'ir.actions.client', 'tag': 'reload'}
                except Exception as e:
                    record.campaign_id.message_post(body=f"Error checking post status: {str(e)}")

        return True

    def action_cancel_scheduled_post(self):
        """Cancel a scheduled post on Facebook."""
        for record in self:
            if record.scheduled_fb_post_id and record.fb_scheduling_status == 'scheduled' and record.campaign_id.fb_access_token:
                try:
                    import requests
                    url = f"https://graph.facebook.com/v17.0/{record.scheduled_fb_post_id}"
                    params = {'access_token': record.campaign_id.fb_access_token}
                    response = requests.delete(url, params=params)

                    if response.status_code in (200, 204):
                        record.write({
                            'scheduled_fb_post_id': False,
                            'fb_scheduling_status': 'draft'
                        })
                        record.campaign_id.message_post(body="Scheduled Facebook post has been cancelled.")
                    else:
                        data = response.json()
                        error_message = data.get('error', {}).get('message', 'Unknown error')
                        record.campaign_id.message_post(body=f"Failed to cancel Facebook post: {error_message}")

                    return {'type': 'ir.actions.client', 'tag': 'reload'}
                except Exception as e:
                    record.campaign_id.message_post(body=f"Error cancelling post: {str(e)}")

        return True