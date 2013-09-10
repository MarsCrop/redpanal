from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.db.models.signals import post_save
from django.core.urlresolvers import reverse

from actstream import action
from taggit.managers import TaggableManager
from taggit.models import Tag



class Message(models.Model):
    msg = models.TextField(verbose_name=_('message'))
    user = models.ForeignKey(User, verbose_name=_('user'), editable=False)
    created_at = models.DateTimeField(verbose_name=_('created at'), auto_now_add=True)
    tags = TaggableManager(verbose_name=_('hashtags'), blank=True)
    mentioned_users = models.ManyToManyField(User, verbose_name=_('hashtags'), blank=True,
                                           null=True, editable=False,
                                           related_name="mentioned_users")
    content_type = models.ForeignKey(ContentType, null=True, editable=False)
    object_id = models.PositiveIntegerField(null=True, editable=False)
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    _msg_html_cache = models.TextField(editable=False, blank=True, null=True)

    def __unicode__(self):
        return mark_safe(self.as_html())

    def as_html(self):
        if not self._msg_html_cache:
            self._msg_html_cache = Message.to_html(self.msg)
            self.save()
        return self._msg_html_cache

    @staticmethod
    def to_html(msg):
        import re
        USER_REGEX = re.compile(r'@(\w+)')
        HASHTAG_REGEX = re.compile(r'#(\w+)')

        def replace_user(match):
            if match:
                username = match.group(1)
                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    return match.group()
                return '<a href="%s">@%s</a>' % (user.get_absolute_url(), username)

        def replace_hashtags(match):
            if match:
                tag = match.group(1)
                try:
                    tagobj = Tag.objects.get(name=tag)
                except Tag.DoesNotExist:
                    return match.group()
                return '<a href="%s">#%s</a>' % (reverse("hashtaged-list", None, (tagobj.slug,)), tag)

        html = re.sub(USER_REGEX, replace_user, msg)
        html = re.sub(HASHTAG_REGEX, replace_hashtags, html)
        return html

    @staticmethod
    def extract_mentioned_users(msg):
        """Returns a list of users that are mentioned with @userfoo @UserBar"""
        words = msg.split()
        users = filter(lambda word: word.startswith('@'), words)
        users = [u[1:] for u in users]
        return User.objects.filter(username__in=users)

    @staticmethod
    def extract_hashtags(msg):
        """Returns the list of hashtags in the msg"""
        msg = msg.replace(".", " ").replace(";", " ").replace(",", " ")
        words = msg.split()
        tags = filter(lambda word: word.startswith('#'), words)
        return [tag[1:] for tag in tags]

    def save(self, *args, **kwargs):
        super(Message, self).save(*args, **kwargs)

        tags = Message.extract_hashtags(self.msg)
        self.tags.clear()
        if tags:
            self.tags.add(*tags)

        mentioned_users = Message.extract_mentioned_users(self.msg)
        self.mentioned_users.clear()
        if mentioned_users:
            self.mentioned_users.add(*mentioned_users)


def message_created_signal(sender, instance, created, **kwargs):
    if created:
        action.send(instance.user, verb=_('commented'), action_object=instance)

post_save.connect(message_created_signal, sender=Message, dispatch_uid="message_created_signal")
