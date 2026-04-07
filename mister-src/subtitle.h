#ifndef SUBTITLE_H_INCLUDED
#define SUBTITLE_H_INCLUDED

// Initialize subtitle socket listener thread
// Listens on /tmp/mister_subtitle.sock for incoming translation text
void subtitle_init();

// Call from main loop — if new subtitle text arrived, display via Info()
void subtitle_poll();

#endif
