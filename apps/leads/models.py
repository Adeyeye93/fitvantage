"""
Leads App Models
================
Consumer lead capture and Twilio integration (Phase 2 scaffolding).
Models for handling lead qualification and provider contact tracking.

Key Models:
- Lead: Consumer inquiries from service pages
- LeadEvent: Status change tracking
- TwilioCall: Phone call tracking
- TwilioMessage: SMS/WhatsApp message tracking
"""

from django.db import models
from django.utils import timezone


class Lead(models.Model):
    """
    Consumer inquiry/lead from a service page.

    Flow:
    1. Consumer submits form on service page (Phase 2)
    2. Lead is created with consumer details
    3. Lead is routed to best ACTIVE provider
    4. Twilio tries to contact provider
    5. If contact successful, lead is marked QUALIFIED
    6. Provider is billed for qualified lead

    Example:
        Consumer: "John Smith", Phone: "07700123456"
        Looking for: "Fitness Training" in "London"
        Assigned to: "John's Fitness Training"
        Status progression: NEW → CONTACTED → QUALIFIED → CONVERTED
    """

    # Consumer details
    name = models.CharField(max_length=200, help_text="Consumer name")
    email = models.EmailField(blank=True, help_text="Consumer email")
    phone = models.CharField(max_length=20, help_text="Consumer phone number")
    whatsapp = models.CharField(
        max_length=20, blank=True, help_text="WhatsApp number (if different from phone)"
    )

    # Service requested
    service = models.CharField(
        max_length=200, help_text="Service consumer is interested in"
    )
    city = models.CharField(
        max_length=100, help_text="City where consumer wants service"
    )

    # Notes from consumer
    notes = models.TextField(blank=True, help_text="Any additional notes from consumer")

    # Provider assignment
    # Using string reference to avoid circular import
    # Will be cast to Provider FK in Phase 2
    provider_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Which provider is handling this lead (provider ID)",
    )

    # Lead status & qualification
    STATUS_CHOICES = [
        ("NEW", "New"),
        ("CONTACTED", "Contacted"),
        ("QUALIFIED", "Qualified"),
        ("CONVERTED", "Converted"),
        ("REJECTED", "Rejected"),
        ("EXPIRED", "Expired"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="NEW",
        help_text="Lead status (QUALIFIED = billable)",
    )

    # Billing
    is_billed = models.BooleanField(
        default=False, help_text="Whether provider has been billed for this lead"
    )
    billed_at = models.DateTimeField(
        null=True, blank=True, help_text="When this lead was billed"
    )
    amount_billed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount provider was charged (GBP)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    qualified_at = models.DateTimeField(
        null=True, blank=True, help_text="When lead became qualified"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["provider_id", "status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["service", "city"]),
        ]

    def __str__(self):
        return f"Lead: {self.name} ({self.service} in {self.city})"

    def mark_as_qualified(self):
        """Mark lead as qualified (billable)"""
        if self.status != "QUALIFIED":
            self.status = "QUALIFIED"
            self.qualified_at = timezone.now()
            self.save()


class LeadEvent(models.Model):
    """
    Track status changes and events for a lead.
    Useful for understanding lead journey and debugging issues.

    Example Events:
        - CREATED: Lead submitted via form
        - ASSIGNED: Routed to a provider
        - CONTACT_ATTEMPT: Called or messaged provider
        - CONTACT_SUCCESS: Provider answered/replied
        - QUALIFIED: Lead becomes billable
        - BILLED: Provider charged
    """

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="Which lead this event is for",
    )

    EVENT_TYPE_CHOICES = [
        ("CREATED", "Lead Created"),
        ("ASSIGNED", "Assigned to Provider"),
        ("CONTACT_ATTEMPT", "Contact Attempt"),
        ("CONTACT_SUCCESS", "Contact Successful"),
        ("CONTACT_FAILED", "Contact Failed"),
        ("QUALIFIED", "Lead Qualified"),
        ("BILLED", "Lead Billed"),
        ("CONVERTED", "Lead Converted"),
        ("REJECTED", "Lead Rejected"),
        ("EXPIRED", "Lead Expired"),
    ]
    event_type = models.CharField(
        max_length=30, choices=EVENT_TYPE_CHOICES, help_text="Type of event"
    )

    description = models.TextField(blank=True, help_text="Additional event details")

    # Who triggered this event
    triggered_by = models.CharField(
        max_length=50,
        choices=[
            ("SYSTEM", "System/Automation"),
            ("PROVIDER", "Provider"),
            ("ADMIN", "Admin"),
            ("TWILIO", "Twilio Webhook"),
        ],
        default="SYSTEM",
        help_text="Who triggered this event",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lead Event"
        verbose_name_plural = "Lead Events"
        indexes = [
            models.Index(fields=["lead", "-created_at"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self):
        return f"{self.lead.name} - {self.get_event_type_display()}"


class TwilioCall(models.Model):
    """
    Track phone calls made to providers via Twilio.

    Used to verify that provider was actually contacted
    (necessary for lead qualification and billing).

    Twilio Flow:
    1. We initiate call to provider's phone number
    2. Twilio sends webhook with call_sid and status
    3. We track if call was answered, went to voicemail, etc.
    4. If answered/voicemail = provider was contacted = lead qualifies
    """

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="twilio_calls",
        help_text="Which lead this call is for",
    )

    # Twilio details
    call_sid = models.CharField(
        max_length=100, unique=True, help_text="Twilio call SID (unique identifier)"
    )
    from_number = models.CharField(max_length=20, help_text="Caller ID number")
    to_number = models.CharField(max_length=20, help_text="Number that was called")

    # Call outcome
    STATUS_CHOICES = [
        ("INITIATED", "Initiated"),
        ("RINGING", "Ringing"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("NO_ANSWER", "No Answer"),
        ("BUSY", "Busy"),
        ("VOICEMAIL", "Voicemail"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="INITIATED",
        help_text="Current call status",
    )

    # Duration
    duration_seconds = models.IntegerField(
        null=True, blank=True, help_text="Call duration in seconds (0 if not answered)"
    )

    # Recording (if enabled)
    recording_url = models.URLField(
        blank=True, help_text="URL to call recording (if available)"
    )

    # Error handling
    error_message = models.TextField(
        blank=True, help_text="Error message if call failed"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Twilio Call"
        verbose_name_plural = "Twilio Calls"
        indexes = [
            models.Index(fields=["call_sid"]),
            models.Index(fields=["status"]),
            models.Index(fields=["lead", "-created_at"]),
        ]

    def __str__(self):
        return f"Call {self.call_sid} - {self.get_status_display()}"

    def was_answered(self):
        """Check if call was actually answered"""
        return self.status in ["COMPLETED", "VOICEMAIL"]


class TwilioMessage(models.Model):
    """
    Track SMS/WhatsApp messages sent to providers via Twilio.

    Used to verify that provider was contacted (necessary for
    lead qualification and billing).

    Twilio Flow:
    1. We send SMS or WhatsApp message to provider
    2. Twilio sends webhook with message_sid and status
    3. We track if message was sent and delivered
    4. If delivered = provider was contacted = lead qualifies
    """

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="twilio_messages",
        help_text="Which lead this message is for",
    )

    # Twilio details
    message_sid = models.CharField(
        max_length=100, unique=True, help_text="Twilio message SID (unique identifier)"
    )
    from_number = models.CharField(max_length=20, help_text="Sender number")
    to_number = models.CharField(max_length=20, help_text="Recipient number")

    # Message details
    MESSAGE_TYPE_CHOICES = [
        ("SMS", "SMS"),
        ("WHATSAPP", "WhatsApp"),
    ]
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE_CHOICES,
        default="SMS",
        help_text="Type of message (SMS or WhatsApp)",
    )

    message_body = models.TextField(help_text="Message content")

    # Delivery status
    STATUS_CHOICES = [
        ("QUEUED", "Queued"),
        ("SENDING", "Sending"),
        ("SENT", "Sent"),
        ("DELIVERED", "Delivered"),
        ("FAILED", "Failed"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="QUEUED",
        help_text="Message delivery status",
    )

    # Error handling
    error_message = models.TextField(
        blank=True, help_text="Error message if delivery failed"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Twilio Message"
        verbose_name_plural = "Twilio Messages"
        indexes = [
            models.Index(fields=["message_sid"]),
            models.Index(fields=["status"]),
            models.Index(fields=["lead", "-created_at"]),
        ]

    def __str__(self):
        return f"Message {self.message_sid} - {self.get_status_display()}"

    def was_delivered(self):
        """Check if message was delivered"""
        return self.status in ["DELIVERED", "SENT"]


__all__ = [
    "Lead",
    "LeadEvent",
    "TwilioCall",
    "TwilioMessage",
]
