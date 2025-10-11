from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.db.models import Count, Sum, Avg
from .models import (
    UserProfile, UserWallet, Transaction, 
    Analyst, CryptoAnalysis, PurchasedAnalysis, 
    AnalysisRating, Category, Consultation, ConsultationPackage,
    SiteSetting, MarketInsight, ChartAnnotation, TechnicalIndicatorData,
    AnalysisInsight, AnalysisMetric, ConsultationAttachment, ConsultationReminder
)

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ['phone_number', 'address', 'profile_picture', 'date_of_birth', 'created_at', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']

class UserWalletInline(admin.StackedInline):
    model = UserWallet
    can_delete = False
    verbose_name_plural = 'Wallet'
    fields = ['balance', 'wallet_id', 'preferred_payment_method', 'mpesa_number', 'paypal_email', 'created_at']
    readonly_fields = ['wallet_id', 'created_at']

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, UserWalletInline)
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined', 'get_balance', 'get_purchases_count']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'date_joined']
    
    def get_balance(self, obj):
        try:
            wallet = obj.userwallet
            return f"${wallet.balance}"
        except UserWallet.DoesNotExist:
            return "$0.00"
    get_balance.short_description = 'Balance'
    
    def get_purchases_count(self, obj):
        return obj.purchasedanalysis_set.count()
    get_purchases_count.short_description = 'Purchases'

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone_number', 'date_of_birth', 'created_at', 'profile_picture_preview']
    search_fields = ['user__username', 'user__email', 'phone_number']
    list_filter = ['created_at', 'date_of_birth']
    readonly_fields = ['created_at', 'updated_at', 'profile_picture_preview']
    
    def profile_picture_preview(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" width="50" height="50" style="border-radius: 50%;" />', obj.profile_picture.url)
        return "No Image"
    profile_picture_preview.short_description = 'Profile Picture'

@admin.register(UserWallet)
class UserWalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance_display', 'preferred_payment_method', 'mpesa_verified', 'paypal_verified', 'created_at']
    search_fields = ['user__username', 'user__email', 'wallet_id']
    list_filter = ['preferred_payment_method', 'mpesa_verified', 'paypal_verified', 'created_at']
    readonly_fields = ['wallet_id', 'created_at', 'updated_at']
    list_editable = ['mpesa_verified', 'paypal_verified']
    
    def balance_display(self, obj):
        return f"${obj.balance:,.2f}"
    balance_display.short_description = 'Balance'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id_short', 'user', 'amount_display', 'transaction_type', 'payment_method', 'status_badge', 'created_at']
    list_filter = ['transaction_type', 'payment_method', 'status', 'created_at']
    search_fields = ['user__username', 'transaction_id', 'mpesa_code', 'paypal_transaction_id', 'description']
    readonly_fields = ['transaction_id', 'created_at', 'updated_at']
    list_per_page = 50
    
    def transaction_id_short(self, obj):
        return str(obj.transaction_id)[:8] + "..."
    transaction_id_short.short_description = 'Transaction ID'
    
    def amount_display(self, obj):
        return f"${obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    
    def status_badge(self, obj):
        colors = {
            'completed': 'green',
            'pending': 'orange',
            'failed': 'red',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

@admin.register(Analyst)
class AnalystAdmin(admin.ModelAdmin):
    list_display = ['user', 'analyst_name', 'experience_years', 'verified', 'total_sales', 'rating_stars', 'joined_date']
    list_filter = ['verified', 'experience_years', 'joined_date']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'specialization']
    readonly_fields = ['joined_date', 'total_sales', 'rating']
    list_editable = ['verified', 'experience_years']
    
    def analyst_name(self, obj):
        return obj.analyst_name
    analyst_name.short_description = 'Name'
    
    def rating_stars(self, obj):
        stars = '★' * int(obj.rating) + '☆' * (5 - int(obj.rating))
        return format_html('<span style="color: gold;">{}</span>', stars)
    rating_stars.short_description = 'Rating'

@admin.register(MarketInsight)
class MarketInsightAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'insight_type_badge', 'cryptocurrency', 
        'urgency_badge', 'impact_level_badge', 'is_verified', 
        'is_featured', 'published_at', 'views_count'
    ]
    list_filter = ['insight_type', 'urgency', 'impact_level', 'is_verified', 'is_featured', 'published_at']
    search_fields = ['title', 'cryptocurrency', 'summary', 'key_takeaways']
    readonly_fields = ['views_count', 'created_at', 'updated_at']
    list_editable = ['is_featured', 'is_verified']
    list_per_page = 20
    
    def insight_type_badge(self, obj):
        colors = {
            'market_trend': 'blue',
            'price_analysis': 'green',
            'regulatory': 'orange',
            'technology': 'purple',
            'adoption': 'teal',
            'security': 'red'
        }
        color = colors.get(obj.insight_type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_insight_type_display()
        )
    insight_type_badge.short_description = 'Type'
    
    def urgency_badge(self, obj):
        colors = {
            'low': 'green',
            'medium': 'orange',
            'high': 'red',
            'critical': 'darkred'
        }
        color = colors.get(obj.urgency, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_urgency_display()
        )
    urgency_badge.short_description = 'Urgency'
    
    def impact_level_badge(self, obj):
        colors = {
            'low': 'blue',
            'medium': 'orange',
            'high': 'red',
            'critical': 'darkred'
        }
        color = colors.get(obj.impact_level, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_impact_level_display()
        )
    impact_level_badge.short_description = 'Impact'

@admin.register(CryptoAnalysis)
class CryptoAnalysisAdmin(admin.ModelAdmin):
    list_display = [
        'cryptocurrency', 'symbol', 'analyst', 'analysis_type', 
        'price_display', 'risk_level_badge', 'recommendation_badge', 
        'is_active', 'is_featured', 'sales_count', 'has_charts', 'created_at'
    ]
    list_filter = ['analysis_type', 'risk_level', 'recommendation', 'is_active', 'is_featured', 'created_at']
    search_fields = ['cryptocurrency', 'symbol', 'analyst__user__username', 'title', 'description']
    readonly_fields = ['sales_count', 'views_count', 'rating', 'created_at', 'updated_at', 'chart_data_preview']
    list_editable = ['is_active', 'is_featured']
    filter_horizontal = []
    
    def price_display(self, obj):
        if obj.discount_percentage > 0:
            return format_html(
                '<span style="text-decoration: line-through; color: gray;">${}</span><br><span style="color: green;">${}</span>',
                obj.price, obj.final_price
            )
        return f"${obj.price}"
    price_display.short_description = 'Price'
    
    def risk_level_badge(self, obj):
        colors = {
            'low': 'green',
            'medium': 'orange',
            'high': 'red'
        }
        color = colors.get(obj.risk_level, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_risk_level_display()
        )
    risk_level_badge.short_description = 'Risk'
    
    def recommendation_badge(self, obj):
        colors = {
            'buy': 'green',
            'strong_buy': 'darkgreen',
            'sell': 'red',
            'strong_sell': 'darkred',
            'hold': 'blue'
        }
        color = colors.get(obj.recommendation, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_recommendation_display()
        )
    recommendation_badge.short_description = 'Recommendation'
    
    def has_charts(self, obj):
        return obj.has_interactive_charts
    has_charts.boolean = True
    has_charts.short_description = 'Charts'
    
    def chart_data_preview(self, obj):
        if obj.chart_data:
            data_points = len(obj.chart_data.get('prices', []))
            return f"{data_points} data points available"
        return "No chart data"
    chart_data_preview.short_description = 'Chart Data'

@admin.register(ChartAnnotation)
class ChartAnnotationAdmin(admin.ModelAdmin):
    list_display = ['analysis', 'type_badge', 'price_level', 'description_short', 'created_at']
    list_filter = ['type', 'created_at']
    search_fields = ['analysis__cryptocurrency', 'description']
    readonly_fields = ['created_at']
    
    def type_badge(self, obj):
        colors = {
            'support': 'green',
            'resistance': 'red',
            'entry': 'blue',
            'exit': 'orange',
            'target': 'purple',
            'stop_loss': 'darkred'
        }
        color = colors.get(obj.type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_type_display()
        )
    type_badge.short_description = 'Type'
    
    def description_short(self, obj):
        if obj.description:
            return obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return "-"
    description_short.short_description = 'Description'

@admin.register(TechnicalIndicatorData)
class TechnicalIndicatorDataAdmin(admin.ModelAdmin):
    list_display = ['analysis', 'indicator_type_badge', 'parameters_display', 'created_at']
    list_filter = ['indicator_type', 'created_at']
    search_fields = ['analysis__cryptocurrency']
    readonly_fields = ['created_at']
    
    def indicator_type_badge(self, obj):
        colors = {
            'sma': 'blue',
            'ema': 'green',
            'rsi': 'orange',
            'macd': 'purple',
            'bollinger': 'teal',
            'stochastic': 'red'
        }
        color = colors.get(obj.indicator_type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_indicator_type_display()
        )
    indicator_type_badge.short_description = 'Indicator'
    
    def parameters_display(self, obj):
        if obj.parameters:
            params = ", ".join([f"{k}: {v}" for k, v in obj.parameters.items()])
            return params[:50] + "..." if len(params) > 50 else params
        return "-"
    parameters_display.short_description = 'Parameters'

@admin.register(AnalysisInsight)
class AnalysisInsightAdmin(admin.ModelAdmin):
    list_display = ['analysis', 'title', 'importance_badge', 'category_badge', 'created_at']
    list_filter = ['importance', 'category', 'created_at']
    search_fields = ['analysis__cryptocurrency', 'title', 'description']
    readonly_fields = ['created_at']
    
    def importance_badge(self, obj):
        colors = {
            'low': 'green',
            'medium': 'orange',
            'high': 'red',
            'critical': 'darkred'
        }
        color = colors.get(obj.importance, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_importance_display()
        )
    importance_badge.short_description = 'Importance'
    
    def category_badge(self, obj):
        colors = {
            'technical': 'blue',
            'fundamental': 'green',
            'sentiment': 'orange',
            'risk': 'red',
            'opportunity': 'purple'
        }
        color = colors.get(obj.category, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_category_display()
        )
    category_badge.short_description = 'Category'

@admin.register(AnalysisMetric)
class AnalysisMetricAdmin(admin.ModelAdmin):
    list_display = ['analysis', 'name', 'current_value', 'previous_value', 'change', 'trend_badge']
    list_filter = ['trend']
    search_fields = ['analysis__cryptocurrency', 'name']
    
    def trend_badge(self, obj):
        colors = {
            'up': 'green',
            'down': 'red',
            'neutral': 'gray'
        }
        color = colors.get(obj.trend, 'blue')
        arrow = {
            'up': '↑',
            'down': '↓',
            'neutral': '→'
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, arrow.get(obj.trend, '→')
        )
    trend_badge.short_description = 'Trend'

@admin.register(PurchasedAnalysis)
class PurchasedAnalysisAdmin(admin.ModelAdmin):
    list_display = ['user', 'analysis', 'purchase_price_display', 'purchased_at', 'access_expires', 'is_expired_badge', 'rating_given_stars']
    list_filter = ['purchased_at', 'access_expires']
    search_fields = ['user__username', 'analysis__cryptocurrency', 'analysis__symbol']
    readonly_fields = ['purchased_at']
    list_per_page = 25
    
    def purchase_price_display(self, obj):
        return f"${obj.purchase_price:,.2f}"
    purchase_price_display.short_description = 'Price'
    
    def is_expired_badge(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: red;">Expired</span>')
        return format_html('<span style="color: green;">Active</span>')
    is_expired_badge.short_description = 'Status'
    
    def rating_given_stars(self, obj):
        if obj.rating_given:
            stars = '★' * obj.rating_given + '☆' * (5 - obj.rating_given)
            return format_html('<span style="color: gold;">{}</span>', stars)
        return "Not Rated"
    rating_given_stars.short_description = 'Rating'

@admin.register(AnalysisRating)
class AnalysisRatingAdmin(admin.ModelAdmin):
    list_display = ['analysis', 'user', 'rating_stars', 'created_at', 'has_review']
    list_filter = ['rating', 'created_at']
    search_fields = ['analysis__cryptocurrency', 'user__username', 'review']
    readonly_fields = ['created_at']
    
    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: gold;">{}</span>', stars)
    rating_stars.short_description = 'Rating'
    
    def has_review(self, obj):
        return bool(obj.review)
    has_review.boolean = True
    has_review.short_description = 'Has Review'

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'analyses_count', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    
    def analyses_count(self, obj):
        return obj.cryptoanalysis_set.count()
    analyses_count.short_description = 'Analyses'

@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'level_badge', 'price_display', 'scheduled_date', 'status_badge', 'created_at']
    list_filter = ['level', 'status', 'scheduled_date', 'created_at']
    search_fields = ['user__username', 'title', 'description', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    
    def price_display(self, obj):
        return f"${obj.price:,.2f}"
    price_display.short_description = 'Price'
    
    def level_badge(self, obj):
        colors = {
            'beginner': 'green',
            'intermediate': 'orange',
            'advanced': 'red'
        }
        color = colors.get(obj.level, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_level_display()
        )
    level_badge.short_description = 'Level'
    
    def status_badge(self, obj):
        colors = {
            'scheduled': 'blue',
            'completed': 'green',
            'cancelled': 'red',
            'pending': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

@admin.register(ConsultationPackage)
class ConsultationPackageAdmin(admin.ModelAdmin):
    list_display = ['title', 'level_badge', 'price_display', 'duration_display', 'is_active', 'created_at']
    list_filter = ['level', 'is_active', 'created_at']
    search_fields = ['title', 'description']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at', 'features_preview']
    
    def level_badge(self, obj):
        colors = {
            'beginner': 'green',
            'intermediate': 'orange',
            'advanced': 'red'
        }
        color = colors.get(obj.level, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_level_display()
        )
    level_badge.short_description = 'Level'
    
    def price_display(self, obj):
        return f"${obj.price:,.2f}"
    price_display.short_description = 'Price'
    
    def duration_display(self, obj):
        return f"{obj.duration_minutes} min"
    duration_display.short_description = 'Duration'
    
    def features_preview(self, obj):
        features = obj.get_features_list()
        if features:
            feature_list = "".join([f"<li>✓ {feature}</li>" for feature in features])
            return format_html(f"<ul style='margin: 0; padding-left: 20px;'>{feature_list}</ul>")
        return "No features specified"
    features_preview.short_description = 'Features Preview'

@admin.register(ConsultationAttachment)
class ConsultationAttachmentAdmin(admin.ModelAdmin):
    list_display = ['consultation', 'file_name', 'file_type', 'uploaded_by', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['consultation__title', 'file_name', 'description']
    readonly_fields = ['uploaded_at']
    
    def file_preview(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return "No file"
    file_preview.short_description = 'File'

@admin.register(ConsultationReminder)
class ConsultationReminderAdmin(admin.ModelAdmin):
    list_display = ['consultation', 'reminder_type_badge', 'scheduled_time', 'is_sent_badge', 'sent_time']
    list_filter = ['reminder_type', 'is_sent', 'scheduled_time']
    search_fields = ['consultation__title', 'consultation__user__username']
    readonly_fields = ['created_at']
    
    def reminder_type_badge(self, obj):
        colors = {
            'email': 'blue',
            'sms': 'green',
            'push': 'orange'
        }
        color = colors.get(obj.reminder_type, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_reminder_type_display()
        )
    reminder_type_badge.short_description = 'Type'
    
    def is_sent_badge(self, obj):
        if obj.is_sent:
            return format_html('<span style="color: green;">✓ Sent</span>')
        return format_html('<span style="color: orange;">Pending</span>')
    is_sent_badge.short_description = 'Status'

@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'hero_video_preview', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'hero_video_preview']
    
    def hero_video_preview(self, obj):
        if obj.hero_video:
            return format_html(
                '<video width="200" height="120" controls style="border-radius: 8px;">'
                '<source src="{}" type="video/mp4">'
                'Your browser does not support the video tag.'
                '</video>',
                obj.hero_video.url
            )
        return "No Video"
    hero_video_preview.short_description = 'Hero Video Preview'
    
    def has_add_permission(self, request):
        # Limit to only one active SiteSetting
        if SiteSetting.objects.filter(is_active=True).exists() and not SiteSetting.objects.count() >= 5:
            return True
        return SiteSetting.objects.count() < 5
    
    def save_model(self, request, obj, form, change):
        # If setting this as active, deactivate others
        if obj.is_active:
            SiteSetting.objects.exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)

# Custom admin site settings
admin.site.site_header = "Cons-App Administration"
admin.site.site_title = "Cons-App Admin Portal"
admin.site.index_title = "Welcome to Cons-App Administration"