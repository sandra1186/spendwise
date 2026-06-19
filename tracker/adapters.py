from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect


class SpendWiseSocialAccountAdapter(DefaultSocialAccountAdapter):
    def on_authentication_error(
        self,
        request,
        provider,
        error=None,
        exception=None,
        extra_context=None,
    ):
        messages.error(
            request,
            'Google sign-in could not be completed. Please try again or sign in with your username and password.',
        )
        raise ImmediateHttpResponse(redirect('login'))
