from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from competition.models import Game
from competition.streaming.youtube import YouTubeLiveService, YouTubeConfigError


class Command(BaseCommand):
    help = "Reconcile YouTube live streams: promote 'preparing' games to 'live' once the field signal is up, or mark them errored on timeout."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing to the database.',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=None,
            help='Override STREAM_RECONCILE_TIMEOUT (seconds) before a preparing stream is marked errored.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        timeout = options['timeout']
        if timeout is None:
            timeout = getattr(settings, 'STREAM_RECONCILE_TIMEOUT', 180)

        games = (
            Game.objects
            .filter(stream_status='preparing')
            .select_related('home_team', 'away_team', 'season__organization')
        )

        now = timezone.now()
        promoted = 0
        errored = 0
        waiting = 0

        for game in games:
            org = game.season.organization
            svc = YouTubeLiveService()
            try:
                health = svc.get_stream_health(org, game.youtube_stream_id) if game.youtube_stream_id else None
            except YouTubeConfigError as e:
                self.stderr.write(f"[{game.id}] health check failed: {e}")
                continue

            if health == 'active':
                if dry_run:
                    self.stdout.write(f"[{game.id}] would promote to live (health=active)")
                    promoted += 1
                elif self._go_live(svc, org, game):
                    self.stdout.write(self.style.SUCCESS(f"[{game.id}] promoted to live"))
                    promoted += 1
                else:
                    self.stderr.write(f"[{game.id}] go-live transition failed; left as preparing")
                continue

            started = game.stream_started_at or now
            if (now - started) > timedelta(seconds=timeout):
                if dry_run:
                    self.stdout.write(f"[{game.id}] would mark errored (health={health}, timed out)")
                else:
                    game.stream_status = 'error'
                    game.stream_error = f"Timed out waiting for signal (health={health})"
                    game.save(update_fields=['stream_status', 'stream_error'])
                    self.stdout.write(self.style.WARNING(f"[{game.id}] marked errored (health={health})"))
                errored += 1
                continue

            waiting += 1
            self.stdout.write(f"[{game.id}] waiting (health={health})")

        self.stdout.write(
            f"Done. promoted={promoted} errored={errored} waiting={waiting} dry_run={dry_run}"
        )

    def _go_live(self, svc, org, game):
        bid = game.youtube_broadcast_id
        err = None
        try:
            svc.transition_broadcast(org, bid, 'live')
        except YouTubeConfigError as e1:
            err = e1
            try:
                svc.transition_broadcast(org, bid, 'testing')
            except YouTubeConfigError as e2:
                err = e2
            try:
                svc.transition_broadcast(org, bid, 'live')
                err = None
            except YouTubeConfigError as e3:
                err = e3
        if err is not None:
            game.stream_error = f"Go-live transition failed: {err}"
            game.save(update_fields=['stream_error'])
            return False
        game.stream_status = 'live'
        game.save(update_fields=['stream_status'])
        return True
