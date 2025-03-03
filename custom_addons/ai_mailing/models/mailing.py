from odoo.exceptions import UserError

from odoo import models, fields, api
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, date
import os
import json
from math import floor

load_dotenv()

class MarketingCampaign(models.Model):
    _name = "marketing.campaign"
    _description = "Marketing Campaign"
    _inherit = ["mail.thread"]

    company_id = fields.Many2one('res.company', string='Company', index=True, default=lambda self: self.env.company)

    # Campaign Basic Information
    name = fields.Char(string="Campaign Name", required=True)
    campaign_type = fields.Selection([
        ('social_media', 'Social Media'),
        ('email_marketing', 'Email Marketing'),
        ('ads', 'Advertising')
    ], string="Campaign Type", required=True)
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled')
    ], string="Status", default='draft')

    content_strategy = fields.Selection([
        ('engagement', 'Engagement'),
        ('sales', 'Sales'),
        ('awareness', 'Brand Awareness')
    ], string="Content Strategy")
    post_frequency = fields.Char(string="Post Frequency",compute="_compute_post_frequency", store=True, default="")
    context = fields.Text(string="Context")
    tag_ids = fields.Many2many('prompt.tag', string='Tags')


    email_ids = fields.One2many('social.email', 'campaign_id', string="Emails")
    whatsapp_ids = fields.One2many('social.whatsapp', 'campaign_id', string="WhatsApp Messages")
    instagram_ids = fields.One2many('social.instagram', 'campaign_id', string="Instagram Posts")
    facebook_ids = fields.One2many('social.facebook', 'campaign_id', string="Facebook Posts")

    # AI-Generated Email Content
    optional_product_ids = fields.Many2many('product.product', string='Optional Products')
    optional_product_tags = fields.Many2many(
        'product.product',
        relation='marketing_campaign_product_tags_rel',
        column1='campaign_id',
        column2='product_id',
        string="Product Tags(optional)",
        compute="_compute_optional_product_tags",
        store=True
    )

    @api.onchange('start_date','end_date')
    def check_date_validity(self):
        s = self.start_date
        e = self.end_date
        if e<=s :
            raise UserError("The end date must be greater than the start date")
        if s<date.today() :
            raise UserError("The start date must be greater than todays date")

    @api.depends('start_date','end_date','email_ids', 'whatsapp_ids', 'instagram_ids', 'facebook_ids')
    def _compute_post_frequency(self):
        for record in self:
            s=self.start_date
            e=self.end_date
            num_weeks = (e - s).days / 7
            total_posts = sum([
                len(record.email_ids),
                len(record.whatsapp_ids),
                len(record.instagram_ids),
                len(record.facebook_ids)
            ])
            if int(num_weeks) > 0:
                record.post_frequency = f"{floor(total_posts / num_weeks):} per week"
            else:
                record.post_frequency = f"{total_posts} this week"

    @api.depends("optional_product_ids")
    def _compute_optional_product_tags(self):
        for record in self:
            record.optional_product_tags = record.optional_product_ids

    def action_confirm(self):
        print("Campaign confirmed!")

    def get_email_publish_dates(self):
        self.ensure_one()

        email_records = self.env['social.email'].search([
            ('campaign_id', '=', self.id)
        ])

        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str
    def get_instagram_publish_dates(self):

        self.ensure_one()


        email_records = self.env['social.instagram'].search([
            ('campaign_id', '=', self.id)
        ])
        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str
    def get_whatsapp_publish_dates(self):
        self.ensure_one()

        email_records = self.env['social.whatsapp'].search([
            ('campaign_id', '=', self.id)
        ])
        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str
    def get_facebook_publish_dates(self):
        self.ensure_one()

        email_records = self.env['social.facebook'].search([
            ('campaign_id', '=', self.id)
        ])
        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str

    def generate_email_prompt(self, context, tags):

        company_name = self.company_id.name if self.company_id else "our company"

        # Extract product tags or set a default
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"

        # Extract content strategy or set a default
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date

        # Get email publish dates and format as a string
        date_with_content_list = self.get_email_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        # Define the AI prompt
        prompt_template = f"""
        You are an AI Email Marketing Assistant. Your task is to generate a JSON-formatted marketing email that is engaging, persuasive, and aligned with the given campaign details.

        **Campaign Details:**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}

        **Instructions:**
        - Craft a **compelling subject line** that encourages email opens.
        - Choose a **posting date and time** that maximizes audience engagement. Format: `YYYY-MM-DD HH:MM:SS`.
        - Personalize the **greeting** to make the email feel tailored to the recipient.
        - Write an engaging **introduction** that captures attention and sets the stage.
        - Highlight key **details**, including features, benefits, and unique selling points of the product or service.
        - Include a **strong call-to-action (CTA)** that motivates the recipient to take the next step.
        - End with a **friendly and professional closing** that reinforces brand credibility.

        **Expected JSON Output Format:**
        ```json
        {{
            "subject_line": "<A compelling subject line>",
            "date_of_post": "<YYYY-MM-DD HH:MM:SS>",
            "greeting": "<A personalized greeting>",
            "introduction": "<An engaging introduction>",
            "details": "<Key features, benefits, and unique selling points>",
            "call_to_action": "<A strong call-to-action>",
            "closing": "<A professional and friendly closing>"
        }}
        ```

        **Requirements:**
        - Ensure the response is a **valid JSON object** with no extraneous text or formatting.
        - Follow a **persuasive marketing tone** tailored to the provided context and audience.
        - Optimize for readability, engagement, and conversion.
        """

        return prompt_template

    def extract_json_content(self,text):
        """Extracts the JSON content by removing characters before the first '{' and after the last '}'."""
        # Find the index of the first '{' and the last '}'
        start_index = text.find('{')
        end_index = text.rfind('}')

        # If both '{' and '}' are found, return the substring between them
        if start_index != -1 and end_index != -1:
            return text[start_index:end_index + 1]

        # If no valid JSON content is found, return an empty string
        return ""

    def action_generate_email_content(self):
        """Generate AI-powered email content and save it as a new record in the social.email model."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        email_prompt = self.generate_email_prompt(context, tags)

        try:
            # Generate content using the AI model
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(email_prompt)
            try:
                r=self.extract_json_content(response.text)
                email_data = json.loads(r)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(email_data.get("date_of_post"), format)
            print(date_object)
            self.env['social.email'].create({
                'campaign_id': self.id,
                'name': email_data.get("subject_line",""),
                'publish_date':date_object,
                'content': f"""
                    {email_data.get("greeting", "")}
                    {email_data.get("introduction", "")}
                    {email_data.get("details", "")}
                    {email_data.get("call_to_action", "")}
                    {email_data.get("closing", "")}
                """.strip(),  # Combine all parts of the email content
            })
            print(self.get_email_publish_dates())
            self.message_post(body="New AI-generated email content has been created successfully.")
        except Exception as e:
            self.message_post(body=f"Error generating email content: {str(e)}")

    def generate_facebook_prompt(self, context, tags):
        # Extract company details safely
        company_name = self.company_id.name if self.company_id else "our company"
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date

        date_with_content_list = self.get_facebook_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        prompt_template = f"""
        You are a **Social Media Marketing Assistant**. Your task is to create a **highly engaging Facebook post** that aligns with the marketing campaign details and drives audience interaction.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}

        ### **Post Requirements**
        - **Headline:** Craft an attention-grabbing, scroll-stopping headline.
        - **Body Text:** Create an engaging post using a mix of compelling copy and relevant emojis 🎯🔥.
        - **Call-to-Action (CTA):** Encourage users to take action (e.g., visit a website, comment, share, or make a purchase).
        - **Hashtags:** Include strategic and trending hashtags to maximize reach and visibility.

        ### **Tone & Style**
        - Ensure the **tone aligns with {company_name}'s brand identity**.
        - Follow the **{content_strategy}** strategy for consistency across campaigns.
        - Adapt the post style for **maximum engagement on Facebook**.

        **Additional Considerations:**
        - Optimize post length for Facebook's algorithm (~40-80 words for engagement).
        - If relevant, suggest a high-quality image or video idea that enhances the post.
        - Ensure the post follows Facebook’s **best practices** for organic reach.

        Please return the Facebook post **as a structured JSON object** in the following format:

        ```json
        {{
            "headline": "<Catchy headline>",
            "body_text": "<Engaging post with emojis>",
            "call_to_action": "<Clear CTA>",
            "hashtags": "<Relevant hashtags>",
            "suggested_post_date": "<YYYY-MM-DD HH:MM:SS>",
            "media_suggestion": "<Optional: Image/video idea>"
        }}
        ```

        Ensure that the output is **valid JSON**, without any extra text or formatting outside of the JSON object.
        """

        return prompt_template

    def action_generate_facebook_content(self):
        """Generate AI-powered Facebook content and save it as a new record."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        facebook_prompt = self.generate_facebook_prompt(context, tags)

        try:
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(facebook_prompt)
            try:
                r = self.extract_json_content(response.text)
                facebook_data = json.loads(r)
                print(facebook_data)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(facebook_data.get("suggested_post_date"), format)
            self.env['social.facebook'].create({
                'campaign_id': self.id,
                'name': facebook_data.get("headline", ""),
                'publish_date': date_object,
                'content': f"""
                                {facebook_data.get("body_text", "")}
                                {facebook_data.get("call_to_action", "")}
                                {facebook_data.get("hashtags", "")}
                                {facebook_data.get("media_suggestion", "")}
                            """.strip(),  # Combine all parts of the email content
            })

        except Exception as e:
            self.message_post(body=f"Error generating Facebook content: {str(e)}")

        self.message_post(body="New AI-generated Facebook content has been created successfully.")

    def generate_instagram_prompt(self, context, tags):

        company_name = self.company_id.name if self.company_id else "our company"
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date

        # Get restricted posting dates
        date_with_content_list = self.get_instagram_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        prompt_template = f"""
        You are a **Social Media Marketing Assistant**. Your task is to create a **highly engaging Instagram post** that aligns with the marketing campaign details and drives audience interaction.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}

        ### **Post Requirements**
        - **Caption:** Write a compelling and engaging caption with a mix of storytelling and brand messaging.
        - **Emojis:** Use emojis 🎯🔥🚀 to make the post visually appealing and engaging.
        - **Call-to-Action (CTA):** Encourage interaction (e.g., "Tag a friend," "Swipe up," "DM us").
        - **Hashtags:** Include trending and relevant hashtags to increase reach.
        - **Image Idea (Optional):** Suggest an ideal image or video concept that fits the post.

        ### **Tone & Style**
        - Ensure the **tone aligns with {company_name}'s brand identity**.
        - Follow the **{content_strategy}** strategy for consistency across campaigns.
        - Adapt the post style for **maximum engagement on Instagram**.

        **Please return the Instagram post in the following structured JSON format:**

        ```json
        {{
            "caption": "<Engaging caption with emojis>",
            "call_to_action": "<Clear CTA>",
            "hashtags": "<Relevant hashtags>",
            "suggested_post_date": "<YYYY-MM-DD HH:MM:SS>",
            "media_suggestion": "<Optional: Image/video idea>"
        }}
        ```

        Ensure that the output is **valid JSON**, without any extra text or formatting outside of the JSON object.
        """

        return prompt_template

    def action_generate_instagram_content(self):
        """Generate AI-powered Instagram content and save it as a new record."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        instagram_prompt = self.generate_instagram_prompt(context, tags)

        print("Generated Instagram Prompt:\n", instagram_prompt)

        try:
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(instagram_prompt)
            try:
                r = self.extract_json_content(response.text)
                instagram_data = json.loads(r)
                print(instagram_data)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(instagram_data.get("suggested_post_date"), format)
            self.env['social.instagram'].create({
                'campaign_id': self.id,
                'name': instagram_data.get("", ""),
                'publish_date': date_object,
                'caption': f"""
                                {instagram_data.get("caption", "")}
                                {instagram_data.get("call_to_action", "")}
                                {instagram_data.get("hashtags", "")}
                                {instagram_data.get("media_suggestion", "")}
                            """.strip(),  # Combine all parts of the email content
            })

        except Exception as e:
            self.message_post(body=f"Error generating Facebook content: {str(e)}")

        self.message_post(body="New AI-generated Facebook content has been created successfully.")

    def generate_whatsapp_prompt(self, context, tags):
        """Generate a structured and engaging WhatsApp marketing message prompt for AI."""

        # Extract company details safely
        company_name = self.company_id.name if self.company_id else "our company"
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date

        # Get restricted posting dates
        date_with_content_list = self.get_whatsapp_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        # Define the AI prompt
        prompt_template = f"""
        You are a **WhatsApp Marketing Assistant**. Your task is to create a **highly engaging WhatsApp message** that aligns with the marketing campaign details and encourages user interaction.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Sending On:** {date_with_content_str}

        ### **Message Requirements**
        - **Greeting:** Start with a warm and friendly greeting (e.g., "Hey there! 😊" or "Hello [First Name]!").
        - **Body Text:** Create a short, engaging message with a mix of text and emojis 🚀🔥 to make it appealing.
        - **Call-to-Action (CTA):** Encourage immediate action (e.g., "Click here to learn more," "Reply with 'YES' to get started").
        - **Closing:** End with a personal and friendly closing (e.g., "Looking forward to hearing from you!" or "Talk soon!").

        ### **Tone & Style**
        - Ensure the **tone matches the brand identity** of {company_name}.
        - Follow the **{content_strategy}** strategy for consistency across campaigns.
        - Make the message **conversational, engaging, and mobile-friendly**.

        **Please return the WhatsApp message in the following structured JSON format:**

        ```json
        {{
            "greeting": "<Personalized greeting>",
            "message_body": "<Engaging message with emojis>",
            "call_to_action": "<Clear CTA>",
            "closing": "<Friendly closing>",
            "suggested_send_time": "<YYYY-MM-DD HH:MM:SS>"
        }}
        ```

        Ensure that the output is **valid JSON**, without any extra text or formatting outside of the JSON object.
        """

        return prompt_template

    def action_generate_whatsapp_content(self):
        """Generate AI-powered WhatsApp content and save it as a new record."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        whatsapp_prompt = self.generate_whatsapp_prompt(context, tags)

        print("Generated WhatsApp Prompt:\n", whatsapp_prompt)

        try:
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(whatsapp_prompt)
            try:
                r = self.extract_json_content(response.text)
                whatsapp_data = json.loads(r)
                print(whatsapp_data)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(whatsapp_data.get("suggested_send_time"), format)
            self.env['social.whatsapp'].create({
                'campaign_id': self.id,
                'name': whatsapp_data.get("", ""),
                'publish_date': date_object,
                'message': f"""
                                {whatsapp_data.get("greeting", "")}
                                {whatsapp_data.get("message_body", "")}
                                {whatsapp_data.get("call_to_action", "")}
                                {whatsapp_data.get("closing", "")}
                            """.strip(),  # Combine all parts of the email content
            })

        except Exception as e:
            self.message_post(body=f"Error generating Facebook content: {str(e)}")

        self.message_post(body="New AI-generated Facebook content has been created successfully.")
