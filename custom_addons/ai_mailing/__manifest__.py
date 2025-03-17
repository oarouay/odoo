{
    "name" : "Generate Email with AI",
    "author" : "Arouay",
    "license" : "LGPL-3",
    "depends" : [
        'mail',
        'sale',
        'product',
        'mass_mailing'
                 ],
    "data" : [
        "security/ir.model.access.csv",
        "views/mailing_ai_views.xml",
        "views/prompt_tag_views.xml",
        "views/social_views.xml",
        "views/media_views.xml",
        "views/social_actions.xml",
        "views/menu_mailing.xml",
    ]
}