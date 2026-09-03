/* cghelper - tiny macOS input helper for computer-automation.
 *
 * One process per action keeps the Python side dependency-free (ctypes
 * cannot pass CGPoint by value on old ARM Python). Moves batch all
 * points through a single spawn. Links only system frameworks.
 *
 * Build: clang -O2 -o ../bin/cghelper cghelper.c -framework CoreGraphics -framework ApplicationServices
 */
#include <ApplicationServices/ApplicationServices.h>
#include <CoreGraphics/CoreGraphics.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void post(CGEventRef e) {
  CGEventPost(kCGHIDEventTap, e);
  CFRelease(e);
}

static void mouse_at(CGEventType type, int x, int y, int btn, int clicks) {
  CGPoint p = CGPointMake((double)x, (double)y);
  CGEventRef e = CGEventCreateMouseEvent(NULL, type, p, (CGMouseButton)btn);
  if (e == NULL) {
    fprintf(stderr, "cghelper: event create failed\n");
    exit(3);
  }
  if (clicks > 0)
    CGEventSetIntegerValueField(e, kCGMouseEventClickState, clicks);
  post(e);
}

static int utf8_decode(const unsigned char **s, UniChar *out) {
  const unsigned char *p = *s;
  if (*p < 0x80) {
    *out = *p;
    *s = p + 1;
    return 1;
  }
  if ((*p & 0xE0) == 0xC0 && (p[1] & 0xC0) == 0x80) {
    *out = (UniChar)(((p[0] & 0x1F) << 6) | (p[1] & 0x3F));
    *s = p + 2;
    return 1;
  }
  if ((*p & 0xF0) == 0xE0 && (p[1] & 0xC0) == 0x80 && (p[2] & 0xC0) == 0x80) {
    *out = (UniChar)(((p[0] & 0x0F) << 12) | ((p[1] & 0x3F) << 6) | (p[2] & 0x3F));
    *s = p + 3;
    return 1;
  }
  *out = (UniChar)'?';
  *s = p + 1;
  return 1;
}

static void usage(void) {
  fprintf(stderr,
          "usage: cghelper <pos|trusted|move x y|movebatch gap_us|click x y btn clicks|drag x1 y1 x2 y2|scroll dy dx|type gap_us|key code flags>\n");
}

int main(int argc, char **argv) {
  if (argc < 2) {
    usage();
    return 2;
  }
  if (strcmp(argv[1], "pos") == 0) {
    CGEventRef t = CGEventCreate(NULL);
    if (t == NULL) {
      fprintf(stderr, "cghelper: create failed\n");
      return 3;
    }
    CGPoint p = CGEventGetLocation(t);
    CFRelease(t);
    printf("%d %d\n", (int)p.x, (int)p.y);
    return 0;
  }
  if (strcmp(argv[1], "trusted") == 0) {
    printf("%d\n", AXIsProcessTrusted() ? 1 : 0);
    return 0;
  }
  if (strcmp(argv[1], "move") == 0 && argc == 4) {
    mouse_at(kCGEventMouseMoved, atoi(argv[2]), atoi(argv[3]), 0, 0);
    return 0;
  }
  if (strcmp(argv[1], "movebatch") == 0 && argc == 3) {
    int gap = atoi(argv[2]);
    int x, y;
    while (scanf("%d %d", &x, &y) == 2) {
      mouse_at(kCGEventMouseMoved, x, y, 0, 0);
      if (gap > 0)
        usleep((useconds_t)gap);
    }
    return 0;
  }
  if (strcmp(argv[1], "click") == 0 && argc == 6) {
    int x = atoi(argv[2]), y = atoi(argv[3]);
    int btn = atoi(argv[4]), n = atoi(argv[5]);
    CGEventType down = btn == 1 ? kCGEventRightMouseDown : kCGEventLeftMouseDown;
    CGEventType up = btn == 1 ? kCGEventRightMouseUp : kCGEventLeftMouseUp;
    for (int i = 1; i <= (n > 2 ? 2 : (n < 1 ? 1 : n)); i++) {
      mouse_at(down, x, y, btn, i);
      mouse_at(up, x, y, btn, 0);
      if (n == 2 && i == 1)
        usleep(80000);
    }
    return 0;
  }
  if (strcmp(argv[1], "drag") == 0 && argc == 6) {
    int x1 = atoi(argv[2]), y1 = atoi(argv[3]);
    int x2 = atoi(argv[4]), y2 = atoi(argv[5]);
    mouse_at(kCGEventLeftMouseDown, x1, y1, 0, 1);
    int x, y;
    while (scanf("%d %d", &x, &y) == 2)
      mouse_at(kCGEventLeftMouseDragged, x, y, 0, 0);
    mouse_at(kCGEventLeftMouseUp, x2, y2, 0, 0);
    return 0;
  }
  if (strcmp(argv[1], "scroll") == 0 && argc == 5) {
    int dy = atoi(argv[2]), dx = atoi(argv[3]), count = atoi(argv[4]);
    // ponytail ultra: loop ticks in C, one spawn per scroll action
    for (int i = 0; i < (count < 1 ? 1 : count); i++) {
      CGEventRef e = CGEventCreateScrollWheelEvent(NULL, kCGScrollEventUnitLine, 2, dy, dx);
      if (e == NULL) {
        fprintf(stderr, "cghelper: scroll create failed\n");
        return 3;
      }
      post(e);
      usleep(50000);
    }
    return 0;
  }
  if (strcmp(argv[1], "type") == 0 && argc == 3) {
    int gap = atoi(argv[2]);
    size_t cap = 4096, len = 0;
    unsigned char *buf = malloc(cap);
    if (!buf)
      return 3;
    size_t n;
    while ((n = fread(buf + len, 1, cap - len - 1, stdin)) > 0) {
      len += n;
      if (len + 1 >= cap) {
        cap *= 2;
        unsigned char *nb = realloc(buf, cap);
        if (!nb) {
          free(buf);
          return 3;
        }
        buf = nb;
      }
    }
    buf[len] = '\0';
    const unsigned char *p = buf;
    UniChar u;
    int count = 0;
    while (*p) {
      utf8_decode(&p, &u);
      for (int down = 1; down >= 0; down--) {
        CGEventRef e = CGEventCreateKeyboardEvent(NULL, (CGKeyCode)0, down ? true : false);
        if (e == NULL) {
          free(buf);
          fprintf(stderr, "cghelper: key create failed\n");
          return 3;
        }
        CGEventKeyboardSetUnicodeString(e, 1, &u);
        post(e);
      }
      count++;
      if (gap > 0)
        usleep((useconds_t)gap);
    }
    free(buf);
    printf("%d\n", count);
    return 0;
  }
  if (strcmp(argv[1], "key") == 0 && argc == 4) {
    int code = atoi(argv[2]);
    long flags = atol(argv[3]);
    for (int down = 1; down >= 0; down--) {
      CGEventRef e = CGEventCreateKeyboardEvent(NULL, (CGKeyCode)code, down ? true : false);
      if (e == NULL) {
        fprintf(stderr, "cghelper: key create failed\n");
        return 3;
      }
      if (flags)
        CGEventSetFlags(e, (CGEventFlags)flags);
      post(e);
    }
    return 0;
  }
  usage();
  return 2;
}
