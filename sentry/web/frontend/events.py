import datetime
import urllib

from django.core.context_processors import csrf
from django.views.decorators.csrf import csrf_protect

from sentry.conf import settings
from sentry.models import Event
from sentry.web.decorators import login_required, can_manage, render_to_response
from sentry.web.forms import ReplayForm
from sentry.utils import get_filters
from sentry.replays import Replayer


@login_required
@can_manage('read_message')
def event_list(request, project):
    filters = []
    for filter_ in get_filters(Event):
        filters.append(filter_(request))

    try:
        page = int(request.GET.get('p', 1))
    except (TypeError, ValueError):
        page = 1

    event_list = Event.objects.filter(project=project).order_by('-datetime')

    # TODO: implement separate API for messages
    any_filter = False
    for filter_ in filters:
        if not filter_.is_set():
            continue
        any_filter = True
        event_list = filter_.get_query_set(event_list)

    offset = (page - 1) * settings.MESSAGES_PER_PAGE
    limit = page * settings.MESSAGES_PER_PAGE

    today = datetime.datetime.now()

    has_realtime = False

    return render_to_response('sentry/events/event_list.html', {
        'project': project,
        'has_realtime': has_realtime,
        'event_list': event_list[offset:limit],
        'today': today,
        'any_filter': any_filter,
        'request': request,
        'filters': filters,
    })


@login_required
@csrf_protect
def replay_event(request, project_id, event_id):
    event = Event.objects.get(pk=event_id)
    interfaces = event.interfaces
    if 'sentry.interfaces.Http' not in interfaces:
        # TODO: show a proper error
        raise ValueError
    http = interfaces['sentry.interfaces.Http']
    initial = {
        'url': http.url,
        'method': http.method,
        'headers': '\n'.join('%s: %s' % (k, v) for k, v in http.env.iteritems()),
        'data': urllib.urlencode(http.data),
    }

    form = ReplayForm(request.POST or None, initial=initial)
    if form.is_valid():
        result = Replayer(
            url=form.cleaned_data['url'],
            method=form.cleaned_data['method'],
            data=form.cleaned_data['data'],
            headers=form.cleaned_data['headers'],
        ).replay()
    else:
        result = None

    context = {
        'request': request,
        'event': event,
        'form': form,
        'result': result,
    }
    context.update(csrf(request))

    return render_to_response('sentry/events/replay_request.html', context)