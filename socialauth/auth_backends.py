import logging
logger = logging.getLogger('socialauth.auth_backends')

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.conf import settings
# import facebook

from socialauth.lib import oauthtwitter
from socialauth.models import OpenidProfile, TwitterUserProfile, FacebookUserProfile, LinkedInUserProfile, AuthMeta
from socialauth.lib.linkedin import *
import urllib
import random


TWITTER_CONSUMER_KEY = getattr(settings, 'TWITTER_CONSUMER_KEY', '')
TWITTER_CONSUMER_SECRET = getattr(settings, 'TWITTER_CONSUMER_SECRET', '')

# Harmonized with Facebook
FACEBOOK_APP_ID = getattr(settings, 'FACEBOOK_APP_ID', '')
FACEBOOK_API_KEY = getattr(settings, 'FACEBOOK_API_KEY', '')
FACEBOOK_SECRET_KEY = getattr(settings, 'FACEBOOK_SECRET_KEY', '')
FACEBOOK_URL = getattr(settings, 'FACEBOOK_URL', 'http://api.facebook.com/restserver.php')

# Linkedin
LINKEDIN_CONSUMER_KEY = getattr(settings, 'LINKEDIN_CONSUMER_KEY', '')
LINKEDIN_CONSUMER_SECRET = getattr(settings, 'LINKEDIN_CONSUMER_SECRET', '')

class OpenIdBackend:
    def authenticate(self, openid_key, request, provider, user=None):
        logger.info("request.GET: %s", request.GET)
        logger.info("request.POST: %s", request.POST)
        logger.info('------------------------------------------ Authenticating against OpenID')
        logger.info("openid_key: %s", openid_key)
        logger.info("provider: %s", provider)
        try:
            assoc = OpenidProfile.objects.get(openid_key = openid_key)
            logger.info('Found a OpenidProfile')
            logger.info("assoc.openid_key: %s", assoc.openid_key)
            logger.info("assoc.user.username: %s", assoc.user.username)
            logger.info("assoc.nickname: %s", assoc.nickname)
            logger.info("assoc.is_username_valid: %s", assoc.is_username_valid)
            logger.info("assoc.email: %s", assoc.email)
            if assoc.email.endswith('@socialauth') and request.openid.ax is not None:
                assoc.email = request.openid.ax.getSingle('http://axschema.org/contact/email', None)
                logger.info('Updating existing OpenidProfile with correct openid email')
                assoc.save()
            return assoc.user
        except OpenidProfile.DoesNotExist:
            #fetch if openid provider provides any simple registration fields
            logger.info('Creating a OpenidProfile')
            nickname = None
            email = None
            if request.openid and request.openid.sreg:
                email = request.openid.sreg.get('email')
                nickname = request.openid.sreg.get('nickname')
            elif request.openid and request.openid.ax:
                email = request.openid.ax.getSingle('http://axschema.org/contact/email', None)

            if nickname is None :
                nickname =  ''.join([random.choice('abcdefghijklmnopqrstuvwxyz') for i in xrange(10)])
            
            name_count = User.objects.filter(username__startswith = nickname).count()
            if name_count:
                username = 'OI-{0}{1}'.format(nickname, name_count + 1)
            else:
                username = 'OI-{0}'.format(nickname)
                
            if email is None :
                valid_username = False
                email =  "{0}@socialauth".format(username)
            else:
                valid_username = True
            if not user:
                user = User.objects.create_user(username, email or '')
                user.set_unusable_password()
                user.save()
    
            #create openid association
            assoc = OpenidProfile()
            assoc.openid_key = openid_key
            assoc.user = user
            if provider == 'Google':
                assoc.needs_google_crossdomain_merge = True
            if email:
                assoc.email = email
            if nickname:
                assoc.nickname = nickname
            if valid_username:
                assoc.is_username_valid = True
            assoc.save()

            logger.info("assoc.openid_key: %s", assoc.openid_key)
            logger.info("assoc.user.username: %s", assoc.user.username)
            logger.info("assoc.nickname: %s", assoc.nickname)
            logger.info("assoc.is_username_valid: %s", assoc.is_username_valid)
            logger.info("assoc.email: %s", assoc.email)

            #Create AuthMeta
            auth_meta = AuthMeta(user = user, provider = provider, 
                provider_model='OpenidProfile', provider_id=assoc.pk)
            auth_meta.save()
            return user
    
    def get_user(self, user_id):
        try:
            user = User.objects.get(pk = user_id)
            return user
        except User.DoesNotExist:
            return None

class LinkedInBackend:
    """LinkedInBackend for authentication
    """
    def authenticate(self, linkedin_access_token, user=None):
        linkedin = LinkedIn(settings.LINKEDIN_CONSUMER_KEY, settings.LINKEDIN_CONSUMER_SECRET)
        # get their profile
        
        profile = ProfileApi(linkedin).getMyProfile(access_token = linkedin_access_token)

        try:
            user_profile = LinkedInUserProfile.objects.get(linkedin_uid = profile.id)
            user = user_profile.user
            return user
        except LinkedInUserProfile.DoesNotExist:
            # Create a new user
            username = 'LI-%s' % profile.id
            if not user:
                user = User(username =  username)
                user.set_unusable_password()
                user.first_name, user.last_name = profile.firstname, profile.lastname
                user.email = '{0}@socialauth'.format(username)
                user.save()
            userprofile = LinkedInUserProfile(user = user, linkedin_uid = profile.id)
            userprofile.save()
            auth_meta = AuthMeta(user=user, provider='LinkedIn').save()
            return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except:
            return None

class TwitterBackend:
    """TwitterBackend for authentication
    """
    def authenticate(self, twitter_access_token, user=None):
        '''authenticates the token by requesting user information from twitter
        '''
        twitter = oauthtwitter.OAuthApi(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, twitter_access_token)
        try:
            userinfo = twitter.GetUserInfo()
        except:
            # If we cannot get the user information, user cannot be authenticated
            raise

        screen_name = userinfo.screen_name
        
        try:
            user_profile = TwitterUserProfile.objects.get(screen_name = screen_name)
            user = user_profile.user
            return user
        except TwitterUserProfile.DoesNotExist:
            # Create new user
            username = "TW-{0}".format(screen_name)
            if not user:
                user = User(username =  username)
                user.set_unusable_password()
                name_data = userinfo.name.split()
                try:
                    first_name, last_name = name_data[0], ' '.join(name_data[1:])
                except:
                    first_name, last_name =  screen_name, ''
                user.first_name, user.last_name = first_name, last_name
                user.email = screen_name + "@socialauth"
                #user.email = '%s@example.twitter.com'%(userinfo.screen_name)
                user.save()
            userprofile = TwitterUserProfile(user = user, screen_name = screen_name)
            # userprofile.access_token = access_token.key
            userprofile.save()
            auth_meta = AuthMeta(user=user, provider='Twitter', 
                provider_model='TwitterUserProfile', provider_id=userprofile.pk).save()
            return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except:
            return None

class FacebookBackend:
    def authenticate(self, request, user=None):
        cookie = facebook.get_user_from_cookie(request.COOKIES,FACEBOOK_APP_ID,FACEBOOK_SECRET_KEY)

        if cookie:
            uid = cookie['uid']
            access_token = cookie['access_token']
        else:
            # if cookie does not exist
            # assume logging in normal way
            params = {}
            params["client_id"] = FACEBOOK_APP_ID
            params["client_secret"] = FACEBOOK_SECRET_KEY
            params["redirect_uri"] = '%s://%s%s' % (
                         'https' if request.is_secure() else 'http',
                         Site.objects.get_current().domain,
                         reverse("socialauth_facebook_login_done"))

            params["code"] = request.GET.get('code', '')

            url = ("https://graph.facebook.com/oauth/access_token?"
                   + urllib.urlencode(params))
            from cgi import parse_qs
            userdata = urllib.urlopen(url).read()
            res_parse_qs = parse_qs(userdata)

            # Could be a bot query
            if not res_parse_qs.has_key('access_token'):
                return None
            
            access_token = res_parse_qs['access_token'][-1]

            graph = facebook.GraphAPI(access_token)
            uid = graph.get_object('me')['id']

        try:
            fb_user = FacebookUserProfile.objects.get(facebook_uid=uid)
            return fb_user.user

        except FacebookUserProfile.DoesNotExist:

            # create new FacebookUserProfile
            graph = facebook.GraphAPI(access_token)
            fb_data = graph.get_object("me")

            if not fb_data:
                return None

            if not user:
                username = 'FB-%s' % fb_data['id']
                user = User.objects.create(username=username)
                user.first_name = fb_data['first_name']
                user.last_name = fb_data['last_name']
                user.email = username + "@socialauth"
                user.set_unusable_password()
                user.save()

            fb_profile = FacebookUserProfile(facebook_uid=uid, user=user)
            fb_profile.save()

            auth_meta = AuthMeta(user=user, provider='Facebook',
                provider_model='FacebookUserProfile', provider_id=fb_profile.pk).save()

            return user


    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except:
            return None
