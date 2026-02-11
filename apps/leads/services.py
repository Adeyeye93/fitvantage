"""
Leads App Services
==================
Business logic for lead management, provider routing, and Twilio integration.

Services:
- LeadService: Lead creation, routing, qualification
- TwilioService: Twilio call and message handling
- ProviderMatchingService: Find best provider for lead
"""

from django.utils import timezone
from django.db.models import Q, Count
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class LeadService:
    """
    Lead management service.

    Handles:
    - Creating leads from forms
    - Routing to providers
    - Qualification tracking
    - Lead lifecycle
    """

    @staticmethod
    def create_lead(
        name, email, phone, whatsapp=None, service=None, city=None, notes=None
    ):
        """
        Create a new lead from consumer form submission.

        Args:
            name: Consumer name
            email: Consumer email
            phone: Consumer phone
            whatsapp: WhatsApp number (optional)
            service: Service requested
            city: City requested
            notes: Additional notes

        Returns:
            Lead instance or error dict
        """
        from apps.leads.models import Lead, LeadEvent

        try:
            # Create lead
            lead = Lead.objects.create(
                name=name,
                email=email,
                phone=phone,
                whatsapp=whatsapp or phone,
                service=service,
                city=city,
                notes=notes,
                status="NEW",
            )

            # Log creation event
            LeadEvent.objects.create(
                lead=lead,
                event_type="CREATED",
                description=f"Lead created for {service} in {city}",
                triggered_by="SYSTEM",
            )

            logger.info(f"Created lead: {lead.id} - {name}")

            return {"success": True, "lead": lead}

        except Exception as e:
            logger.error(f"Error creating lead: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def route_lead_to_provider(lead):
        """
        Route lead to best available provider.

        Args:
            lead: Lead instance

        Returns:
            Provider instance or None
        """
        from apps.leads.models import LeadEvent

        # Find best provider
        provider = ProviderMatchingService.get_best_provider(
            service=lead.service, city=lead.city
        )

        if provider:
            lead.provider_id = provider.id
            lead.status = "CONTACTED"
            lead.save()

            # Log assignment
            LeadEvent.objects.create(
                lead=lead,
                event_type="ASSIGNED",
                description=f"Assigned to {provider.name}",
                triggered_by="SYSTEM",
            )

            logger.info(f"Lead {lead.id} routed to provider {provider.id}")
            return provider

        else:
            logger.warning(f"No provider found for {lead.service} in {lead.city}")
            return None

    @staticmethod
    def mark_lead_qualified(lead, triggered_by="SYSTEM"):
        """
        Mark lead as qualified (ready to bill).

        Args:
            lead: Lead instance
            triggered_by: Who triggered this ('SYSTEM', 'PROVIDER', 'ADMIN', 'TWILIO')
        """
        from apps.leads.models import LeadEvent

        if lead.status == "QUALIFIED":
            return  # Already qualified

        lead.status = "QUALIFIED"
        lead.qualified_at = timezone.now()
        lead.save()

        # Log qualification
        LeadEvent.objects.create(
            lead=lead,
            event_type="QUALIFIED",
            description="Lead became qualified for billing",
            triggered_by=triggered_by,
        )

        logger.info(f"Lead {lead.id} marked as QUALIFIED")

    @staticmethod
    def contact_provider_via_twilio(lead, provider):
        """
        Initiate Twilio contact with provider.

        Args:
            lead: Lead instance
            provider: Provider instance

        Returns:
            dict with contact attempt result
        """
        from apps.leads.models import LeadEvent

        # Determine contact method
        contact_method = provider.contact_method or "PHONE"

        try:
            if contact_method in ["PHONE", "WHATSAPP"]:
                # Make call
                result = TwilioService.make_call(
                    to_number=provider.phone,
                    message=f"You have a new lead: {lead.name} - {lead.service} in {lead.city}",
                )
            else:
                # Send message
                result = TwilioService.send_message(
                    to_number=provider.phone,
                    message=f"New lead: {lead.name} seeking {lead.service} in {lead.city}. Contact them at {lead.phone}",
                )

            if result.get("success"):
                # Log contact attempt
                LeadEvent.objects.create(
                    lead=lead,
                    event_type="CONTACT_ATTEMPT",
                    description=f"Attempted contact via {contact_method}",
                    triggered_by="TWILIO",
                )

                return result
            else:
                # Log failure
                LeadEvent.objects.create(
                    lead=lead,
                    event_type="CONTACT_FAILED",
                    description=result.get("error", "Contact failed"),
                    triggered_by="SYSTEM",
                )

                return result

        except Exception as e:
            logger.error(f"Error contacting provider: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_lead_stats(time_period="today"):
        """
        Get statistics about leads.

        Args:
            time_period: 'today', 'week', 'month', 'all'

        Returns:
            dict with statistics
        """
        from apps.leads.models import Lead
        from datetime import timedelta

        now = timezone.now()

        # Determine date range
        if time_period == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_period == "week":
            start_date = now - timedelta(days=7)
        elif time_period == "month":
            start_date = now - timedelta(days=30)
        else:
            start_date = None

        # Query leads
        query = (
            Lead.objects.all()
            if not start_date
            else Lead.objects.filter(created_at__gte=start_date)
        )

        stats = {
            "total": query.count(),
            "new": query.filter(status="NEW").count(),
            "contacted": query.filter(status="CONTACTED").count(),
            "qualified": query.filter(status="QUALIFIED").count(),
            "converted": query.filter(status="CONVERTED").count(),
            "rejected": query.filter(status="REJECTED").count(),
            "expired": query.filter(status="EXPIRED").count(),
        }

        # Calculate conversion rate
        if stats["total"] > 0:
            stats["conversion_rate"] = (stats["qualified"] / stats["total"]) * 100
        else:
            stats["conversion_rate"] = 0

        return stats

    @staticmethod
    def get_lead_for_display(lead_id):
        """
        Get lead with all related data for display.

        Args:
            lead_id: Lead ID

        Returns:
            dict with lead and related info
        """
        from apps.leads.models import Lead

        try:
            lead = Lead.objects.get(id=lead_id)

            return {
                "lead": lead,
                "provider": lead.provider_id if lead.provider_id else None,
                "events": lead.events.all().order_by("-created_at"),
                "calls": lead.twilio_calls.all().order_by("-created_at"),
                "messages": lead.twilio_messages.all().order_by("-created_at"),
                "time_to_qualified": (
                    (lead.qualified_at - lead.created_at) if lead.qualified_at else None
                ),
            }

        except Lead.DoesNotExist:
            return None


class ProviderMatchingService:
    """
    Find the best provider for a lead based on:
    - Service offered
    - City coverage
    - Active status
    - Rating
    - Availability
    """

    @staticmethod
    def get_best_provider(service, city):
        """
        Find best available provider for a service-city combo.

        Ranking:
        1. Active providers
        2. Covering the service + city
        3. Higher rating
        4. Fewer leads received recently

        Args:
            service: Service name (e.g., "Fitness Training")
            city: City name (e.g., "London")

        Returns:
            Provider instance or None
        """
        from apps.providers.models import Provider, ProviderCoverage

        try:
            # Find providers covering this service-city
            providers = Provider.objects.filter(status="ACTIVE")

            # Filter by service coverage
            providers_with_service = []
            for provider in providers:
                # Check if provider offers this service
                if service in provider.services:
                    # Check if provider covers this city
                    if city in provider.cities:
                        providers_with_service.append(provider)

            if not providers_with_service:
                logger.warning(f"No providers for {service} in {city}")
                return None

            # Rank by rating (highest first)
            ranked = sorted(
                providers_with_service,
                key=lambda p: (-(p.rating or 0), p.total_leads_received),
            )

            # Return top provider
            return ranked[0] if ranked else None

        except Exception as e:
            logger.error(f"Error matching provider: {e}")
            return None

    @staticmethod
    def get_providers_for_service_city(service, city):
        """
        Get all active providers for a service-city combo.

        Args:
            service: Service name
            city: City name

        Returns:
            QuerySet of providers
        """
        from apps.providers.models import Provider

        providers = []

        for provider in Provider.objects.filter(status="ACTIVE"):
            if service in provider.services and city in provider.cities:
                providers.append(provider)

        # Sort by rating (highest first)
        return sorted(providers, key=lambda p: -(p.rating or 0))


class TwilioService:
    """
    Twilio integration for calling and messaging providers.

    Handles:
    - Making phone calls
    - Sending SMS/WhatsApp
    - Receiving webhooks
    - Recording call/message status
    """

    @staticmethod
    def make_call(to_number, message=None, lead_id=None):
        """
        Initiate a call to a provider via Twilio.

        Args:
            to_number: Recipient phone number
            message: TTS message to say (optional)
            lead_id: Associated lead ID

        Returns:
            dict with call_sid and status
        """
        from apps.leads.models import TwilioCall, Lead

        try:
            # In production, use real Twilio SDK:
            # from twilio.rest import Client
            # client = Client(account_sid, auth_token)
            # call = client.calls.create(...)

            # For now, this is a placeholder
            import uuid
            from django.conf import settings

            call_sid = str(uuid.uuid4())

            # Create call record
            call = TwilioCall.objects.create(
                lead_id=lead_id,
                call_sid=call_sid,
                from_number=settings.TWILIO_PHONE_NUMBER or "+447700000000",
                to_number=to_number,
                status="INITIATED",
            )

            logger.info(f"Call initiated: {call_sid} to {to_number}")

            return {
                "success": True,
                "call_sid": call_sid,
                "status": "INITIATED",
            }

        except Exception as e:
            logger.error(f"Error making call: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def send_message(to_number, message, message_type="SMS", lead_id=None):
        """
        Send SMS or WhatsApp message to provider.

        Args:
            to_number: Recipient number
            message: Message text
            message_type: 'SMS' or 'WHATSAPP'
            lead_id: Associated lead ID

        Returns:
            dict with message_sid and status
        """
        from apps.leads.models import TwilioMessage, Lead

        try:
            # In production:
            # from twilio.rest import Client
            # client.messages.create(...)

            import uuid
            from django.conf import settings

            message_sid = str(uuid.uuid4())

            # Create message record
            msg = TwilioMessage.objects.create(
                lead_id=lead_id,
                message_sid=message_sid,
                from_number=settings.TWILIO_PHONE_NUMBER or "+447700000000",
                to_number=to_number,
                message_type=message_type,
                message_body=message,
                status="QUEUED",
            )

            logger.info(f"Message queued: {message_sid} to {to_number}")

            return {
                "success": True,
                "message_sid": message_sid,
                "status": "QUEUED",
            }

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def handle_webhook(data):
        """
        Handle incoming Twilio webhook (call/message status update).

        Twilio will POST to this endpoint when:
        - Call is answered/missed/failed
        - Message is delivered/failed

        Args:
            data: Webhook payload from Twilio

        Returns:
            dict with processing result
        """
        from apps.leads.models import TwilioCall, TwilioMessage, Lead

        try:
            # Determine if call or message
            if "CallSid" in data:
                return TwilioService._handle_call_webhook(data)
            elif "MessageSid" in data:
                return TwilioService._handle_message_webhook(data)
            else:
                return {"success": False, "error": "Unknown webhook type"}

        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _handle_call_webhook(data):
        """Handle call status webhook from Twilio."""
        from apps.leads.models import TwilioCall, Lead

        try:
            call_sid = data.get("CallSid")
            call_status = data.get("CallStatus")

            # Find call record
            call = TwilioCall.objects.get(call_sid=call_sid)

            # Update status
            call.status = call_status.upper()
            call.duration_seconds = int(data.get("CallDuration", 0))
            call.save()

            # If answered/voicemail, mark lead as qualified
            if call_status in ["completed", "answered"]:
                if call.lead:
                    LeadService.mark_lead_qualified(call.lead, triggered_by="TWILIO")

            logger.info(f"Call {call_sid} status: {call_status}")

            return {"success": True, "call_sid": call_sid, "status": call_status}

        except TwilioCall.DoesNotExist:
            logger.warning(f"Call not found: {call_sid}")
            return {"success": False, "error": "Call not found"}

    @staticmethod
    def _handle_message_webhook(data):
        """Handle message status webhook from Twilio."""
        from apps.leads.models import TwilioMessage

        try:
            message_sid = data.get("MessageSid")
            message_status = data.get("MessageStatus")

            # Find message record
            message = TwilioMessage.objects.get(message_sid=message_sid)

            # Update status
            message.status = message_status.upper()
            message.save()

            # If delivered, mark lead as qualified
            if message_status in ["delivered", "sent"]:
                if message.lead:
                    LeadService.mark_lead_qualified(message.lead, triggered_by="TWILIO")

            logger.info(f"Message {message_sid} status: {message_status}")

            return {
                "success": True,
                "message_sid": message_sid,
                "status": message_status,
            }

        except TwilioMessage.DoesNotExist:
            logger.warning(f"Message not found: {message_sid}")
            return {"success": False, "error": "Message not found"}


class BillingService:
    """
    Handle provider billing for qualified leads.
    """

    @staticmethod
    def calculate_lead_cost(lead):
        """
        Calculate how much provider should be charged for a lead.

        Args:
            lead: Lead instance

        Returns:
            Decimal amount in GBP
        """
        if not lead.provider:
            return Decimal("0.00")

        # Use provider's price per lead
        price = lead.provider.price_per_lead or Decimal("0.00")

        # Check for location-based pricing override
        from apps.providers.models import ProviderCoverage

        try:
            coverage = ProviderCoverage.objects.get(
                provider=lead.provider, service=lead.service, city=lead.city
            )

            if coverage.price_for_this_location:
                price = coverage.price_for_this_location

        except ProviderCoverage.DoesNotExist:
            pass

        return price

    @staticmethod
    def bill_lead(lead):
        """
        Bill a qualified lead to provider.

        Args:
            lead: Lead instance

        Returns:
            dict with billing result
        """
        from apps.leads.models import LeadEvent

        try:
            if lead.is_billed:
                return {"success": False, "error": "Already billed"}

            if lead.status != "QUALIFIED":
                return {"success": False, "error": "Lead not qualified"}

            # Calculate cost
            amount = BillingService.calculate_lead_cost(lead)

            # Update lead
            lead.is_billed = True
            lead.billed_at = timezone.now()
            lead.amount_billed = amount
            lead.save()

            # Log billing
            LeadEvent.objects.create(
                lead=lead,
                event_type="BILLED",
                description=f"Billed £{amount} to {lead.provider.name}",
                triggered_by="SYSTEM",
            )

            # Update provider stats
            lead.provider.total_leads_received += 1
            lead.provider.total_paid += amount
            lead.provider.save()

            logger.info(
                f"Lead {lead.id} billed £{amount} to provider {lead.provider.id}"
            )

            return {
                "success": True,
                "amount": amount,
                "provider_id": lead.provider.id,
            }

        except Exception as e:
            logger.error(f"Billing error: {e}")
            return {"success": False, "error": str(e)}


__all__ = [
    "LeadService",
    "ProviderMatchingService",
    "TwilioService",
    "BillingService",
]
