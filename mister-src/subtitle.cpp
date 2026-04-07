#include "subtitle.h"
#include "menu.h"

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/un.h>

#define SUBTITLE_SOCK_PATH "/tmp/mister_subtitle.sock"
#define SUBTITLE_MAX_LEN   512
#define SUBTITLE_DISPLAY_MS 5000

static pthread_t        s_thread;
static pthread_mutex_t  s_mutex = PTHREAD_MUTEX_INITIALIZER;
static char             s_pending[SUBTITLE_MAX_LEN] = {};
static int              s_has_pending = 0;

// ── socket listener thread ────────────────────────────────────────────────
static void *subtitle_thread(void *)
{
	// remove stale socket
	unlink(SUBTITLE_SOCK_PATH);

	int srv = socket(AF_UNIX, SOCK_STREAM, 0);
	if (srv < 0) { perror("[subtitle] socket"); return nullptr; }

	struct sockaddr_un addr = {};
	addr.sun_family = AF_UNIX;
	strncpy(addr.sun_path, SUBTITLE_SOCK_PATH, sizeof(addr.sun_path) - 1);

	if (bind(srv, (struct sockaddr*)&addr, sizeof(addr)) < 0)
	{
		perror("[subtitle] bind");
		close(srv);
		return nullptr;
	}

	listen(srv, 4);
	printf("[subtitle] Listening on %s\n", SUBTITLE_SOCK_PATH);

	while (1)
	{
		int cli = accept(srv, nullptr, nullptr);
		if (cli < 0) continue;

		char buf[SUBTITLE_MAX_LEN] = {};
		int n = read(cli, buf, sizeof(buf) - 1);
		close(cli);

		if (n > 0)
		{
			buf[n] = '\0';
			// strip trailing newline
			while (n > 0 && (buf[n-1] == '\n' || buf[n-1] == '\r')) buf[--n] = '\0';

			if (n > 0)
			{
				pthread_mutex_lock(&s_mutex);
				strncpy(s_pending, buf, SUBTITLE_MAX_LEN - 1);
				s_has_pending = 1;
				pthread_mutex_unlock(&s_mutex);
				printf("[subtitle] Received: %s\n", buf);
			}
		}
	}
	return nullptr;
}

// ── public API ───────────────────────────────────────────────────────────

void subtitle_init()
{
	pthread_attr_t attr;
	pthread_attr_init(&attr);
	pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
	pthread_create(&s_thread, &attr, subtitle_thread, nullptr);
	pthread_attr_destroy(&attr);
}

// Called from main loop every frame — non-blocking
void subtitle_poll()
{
	pthread_mutex_lock(&s_mutex);
	if (s_has_pending)
	{
		char text[SUBTITLE_MAX_LEN];
		strncpy(text, s_pending, SUBTITLE_MAX_LEN - 1);
		s_has_pending = 0;
		pthread_mutex_unlock(&s_mutex);

		// Display at bottom of screen, no frame border, 5 seconds
		Info(text, SUBTITLE_DISPLAY_MS, 0, 0, 1);
	}
	else
	{
		pthread_mutex_unlock(&s_mutex);
	}
}
