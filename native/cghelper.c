/* cghelper - tiny macOS input helper for computer-automation.
 *
 * One process per action keeps the Python side dependency-free (ctypes
 * cannot pass CGPoint by value on old ARM Python). Moves batch all
 * points through a single spawn. Links only system frameworks.
 *
 * Build: mkdir -p ../build && clang -O2 -o ../build/cghelper cghelper.c -framework CoreGraphics -framework ApplicationServices
 */
#include <ApplicationServices/ApplicationServices.h>
#include <CoreGraphics/CoreGraphics.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested = 0;

static void request_stop(int signal_number) {
  (void)signal_number;
  stop_requested = 1;
}

static void post(CGEventRef e) {
  CGEventPost(kCGHIDEventTap, e);
  CFRelease(e);
}

static void finish_keyboard_delivery(void) {
  /* CGEventPost queues delivery. Keep this short-lived source alive while
   * WindowServer consumes the events; immediate exit drops zero-gap keys on
   * the live macOS host. This is per command, not a per-character delay. */
  CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.02, false);
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

static int utf8_decode(const unsigned char **s, UniChar out[2]) {
  const unsigned char *p = *s;
  if (*p < 0x80) {
    out[0] = *p;
    *s = p + 1;
    return 1;
  }
  if (p[1] != '\0' && (*p & 0xE0) == 0xC0 &&
      (p[1] & 0xC0) == 0x80) {
    out[0] = (UniChar)(((p[0] & 0x1F) << 6) | (p[1] & 0x3F));
    *s = p + 2;
    return 1;
  }
  if (p[1] != '\0' && p[2] != '\0' && (*p & 0xF0) == 0xE0 &&
      (p[1] & 0xC0) == 0x80 && (p[2] & 0xC0) == 0x80) {
    out[0] = (UniChar)(((p[0] & 0x0F) << 12) |
                       ((p[1] & 0x3F) << 6) | (p[2] & 0x3F));
    *s = p + 3;
    return 1;
  }
  if (p[1] != '\0' && p[2] != '\0' && p[3] != '\0' &&
      (*p & 0xF8) == 0xF0 && (p[1] & 0xC0) == 0x80 &&
      (p[2] & 0xC0) == 0x80 && (p[3] & 0xC0) == 0x80) {
    uint32_t scalar = ((uint32_t)(p[0] & 0x07) << 18) |
                      ((uint32_t)(p[1] & 0x3F) << 12) |
                      ((uint32_t)(p[2] & 0x3F) << 6) |
                      (uint32_t)(p[3] & 0x3F);
    if (scalar >= 0x10000 && scalar <= 0x10FFFF) {
      scalar -= 0x10000;
      out[0] = (UniChar)(0xD800 + (scalar >> 10));
      out[1] = (UniChar)(0xDC00 + (scalar & 0x3FF));
      *s = p + 4;
      return 2;
    }
  }
  out[0] = (UniChar)'?';
  *s = p + 1;
  return 1;
}

static int type_stdin(int gap) {
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
  UniChar units[2];
  int count = 0;
  while (*p && !stop_requested) {
    int unit_count = utf8_decode(&p, units);
    for (int down = 1; down >= 0; down--) {
      CGEventRef e = CGEventCreateKeyboardEvent(NULL, (CGKeyCode)0, down ? true : false);
      if (e == NULL) {
        free(buf);
        fprintf(stderr, "cghelper: key create failed\n");
        return 3;
      }
      CGEventKeyboardSetUnicodeString(e, (UniCharCount)unit_count, units);
      CGEventSetFlags(e, 0);
      post(e);
    }
    count++;
    // gap applies between events only: sleep BEFORE the next char, never
    // after the last one (a trailing sleep cannot aid delivery)
    if (p[0] && gap > 0)
      usleep((useconds_t)gap);
  }
  free(buf);
  finish_keyboard_delivery();
  printf("%d\n", count);
  fflush(stdout);
  return stop_requested ? 130 : 0;
}

static void usage(void) {
  fprintf(stderr,
          "usage: cghelper <pos|displays|frontmost|focused|element x y|trusted|screen-recording|move x y|movebatch gap_us|click x y btn clicks|drag x1 y1 x2 y2|scroll dy dx|type gap_us|key code flags|release>\n");
}

static int requires_accessibility(const char *command) {
  return strcmp(command, "move") == 0 || strcmp(command, "movebatch") == 0 ||
         strcmp(command, "click") == 0 || strcmp(command, "drag") == 0 ||
         strcmp(command, "scroll") == 0 || strcmp(command, "type") == 0 ||
         strcmp(command, "key") == 0 || strcmp(command, "release") == 0;
}

static int print_display_layout(void) {
  uint32_t count = 0;
  if (CGGetActiveDisplayList(0, NULL, &count) != kCGErrorSuccess || count == 0 ||
      count > 128) {
    fprintf(stderr, "cghelper: display layout unavailable\n");
    return 4;
  }
  CGDirectDisplayID *ids = calloc(count, sizeof(CGDirectDisplayID));
  if (ids == NULL)
    return 3;
  uint32_t actual = 0;
  if (CGGetActiveDisplayList(count, ids, &actual) != kCGErrorSuccess ||
      actual == 0) {
    free(ids);
    fprintf(stderr, "cghelper: display layout unavailable\n");
    return 4;
  }
  CGRect bounds = CGRectNull;
  for (uint32_t i = 0; i < actual; i++)
    bounds = CGRectIsNull(bounds) ? CGDisplayBounds(ids[i])
                                 : CGRectUnion(bounds, CGDisplayBounds(ids[i]));

  printf("{\"origin\":[%.0f,%.0f],\"width\":%.0f,\"height\":%.0f,\"displays\":[",
         bounds.origin.x, bounds.origin.y, bounds.size.width, bounds.size.height);
  for (uint32_t i = 0; i < actual; i++) {
    CGRect display = CGDisplayBounds(ids[i]);
    size_t pixels_wide = CGDisplayPixelsWide(ids[i]);
    size_t pixels_high = CGDisplayPixelsHigh(ids[i]);
    double scale_x = display.size.width > 0
                         ? (double)pixels_wide / display.size.width
                         : 0.0;
    double scale_y = display.size.height > 0
                         ? (double)pixels_high / display.size.height
                         : 0.0;
    if (i > 0)
      putchar(',');
    printf("{\"id\":%u,\"origin\":[%.0f,%.0f],\"width\":%.0f,\"height\":%.0f,"
           "\"scale\":[%.6g,%.6g],\"rotation\":%.6g,\"primary\":%s}",
           ids[i], display.origin.x, display.origin.y, display.size.width,
           display.size.height, scale_x, scale_y, CGDisplayRotation(ids[i]),
           CGDisplayIsMain(ids[i]) ? "true" : "false");
  }
  printf("]}\n");
  free(ids);
  return 0;
}

static CFStringRef copy_string_attribute(AXUIElementRef element,
                                         CFStringRef attribute) {
  CFTypeRef value = NULL;
  if (element == NULL ||
      AXUIElementCopyAttributeValue(element, attribute, &value) !=
          kAXErrorSuccess ||
      value == NULL)
    return NULL;
  if (CFGetTypeID(value) != CFStringGetTypeID()) {
    CFRelease(value);
    return NULL;
  }
  return (CFStringRef)value;
}

static void print_json_string(CFStringRef value) {
  char bytes[4096] = "";
  if (value != NULL)
    CFStringGetCString(value, bytes, sizeof(bytes), kCFStringEncodingUTF8);
  putchar('"');
  for (const unsigned char *p = (const unsigned char *)bytes; *p; p++) {
    if (*p == '"' || *p == '\\') {
      putchar('\\');
      putchar(*p);
    } else if (*p < 0x20) {
      printf("\\u%04x", *p);
    } else {
      putchar(*p);
    }
  }
  putchar('"');
}

static int print_element_metadata(AXUIElementRef element) {
  AXUIElementRef window = NULL;
  AXUIElementCopyAttributeValue(element, kAXWindowAttribute,
                                (CFTypeRef *)&window);
  CFStringRef role = copy_string_attribute(element, kAXRoleAttribute);
  CFStringRef subrole = copy_string_attribute(element, kAXSubroleAttribute);
  CFStringRef title = copy_string_attribute(element, kAXTitleAttribute);
  CFStringRef description =
      copy_string_attribute(element, kAXDescriptionAttribute);
  CFStringRef placeholder =
      copy_string_attribute(element, kAXPlaceholderValueAttribute);
  CFStringRef window_title = copy_string_attribute(window, kAXTitleAttribute);
  CFStringRef window_role = copy_string_attribute(window, kAXRoleAttribute);
  CFStringRef window_subrole = copy_string_attribute(window, kAXSubroleAttribute);

  printf("{\"role\":"); print_json_string(role);
  printf(",\"subrole\":"); print_json_string(subrole);
  printf(",\"title\":"); print_json_string(title);
  printf(",\"description\":"); print_json_string(description);
  printf(",\"placeholder\":"); print_json_string(placeholder);
  printf(",\"window_title\":"); print_json_string(window_title);
  printf(",\"window_role\":"); print_json_string(window_role);
  printf(",\"window_subrole\":"); print_json_string(window_subrole);
  printf("}\n");

  if (window_subrole) CFRelease(window_subrole);
  if (window_role) CFRelease(window_role);
  if (window_title) CFRelease(window_title);
  if (placeholder) CFRelease(placeholder);
  if (description) CFRelease(description);
  if (title) CFRelease(title);
  if (subrole) CFRelease(subrole);
  if (role) CFRelease(role);
  if (window) CFRelease(window);
  return 0;
}

static int print_focused_metadata(void) {
  if (!AXIsProcessTrusted()) {
    fprintf(stderr, "cghelper: Accessibility trust missing\n");
    return 5;
  }
  AXUIElementRef system = AXUIElementCreateSystemWide();
  AXUIElementRef app = NULL, element = NULL;
  if (system == NULL ||
      AXUIElementCopyAttributeValue(system, kAXFocusedApplicationAttribute,
                                    (CFTypeRef *)&app) != kAXErrorSuccess ||
      app == NULL ||
      AXUIElementCopyAttributeValue(app, kAXFocusedUIElementAttribute,
                                    (CFTypeRef *)&element) != kAXErrorSuccess ||
      element == NULL) {
    if (element) CFRelease(element);
    if (app) CFRelease(app);
    if (system) CFRelease(system);
    fprintf(stderr, "cghelper: focused element unavailable\n");
    return 4;
  }
  int result = print_element_metadata(element);
  CFRelease(element);
  CFRelease(app);
  CFRelease(system);
  return result;
}

static int print_position_metadata(int x, int y) {
  if (!AXIsProcessTrusted()) {
    fprintf(stderr, "cghelper: Accessibility trust missing\n");
    return 5;
  }
  AXUIElementRef system = AXUIElementCreateSystemWide();
  AXUIElementRef element = NULL;
  if (system == NULL ||
      AXUIElementCopyElementAtPosition(system, (float)x, (float)y, &element) !=
          kAXErrorSuccess ||
      element == NULL) {
    if (element) CFRelease(element);
    if (system) CFRelease(system);
    fprintf(stderr, "cghelper: coordinate element unavailable\n");
    return 4;
  }
  int result = print_element_metadata(element);
  CFRelease(element);
  CFRelease(system);
  return result;
}

static int print_frontmost_window_owner(void) {
  /* CGWindowListCopyWindowInfo does not guarantee front-to-back order.
   * The Python layer's JXA-based active_window() is the primary path;
   * this is a C fallback. Skip hidden/zero-size windows to avoid
   * picking up overlay processes like Cua Driver. */
  CFArrayRef windows = CGWindowListCopyWindowInfo(
      kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
      kCGNullWindowID);
  if (windows == NULL)
    return 3;
  CFIndex count = CFArrayGetCount(windows);
  for (CFIndex i = 0; i < count; i++) {
    CFDictionaryRef window = (CFDictionaryRef)CFArrayGetValueAtIndex(windows, i);
    CFNumberRef layer_value = (CFNumberRef)CFDictionaryGetValue(window, kCGWindowLayer);
    int layer = -1;
    if (layer_value == NULL || !CFNumberGetValue(layer_value, kCFNumberIntType, &layer) || layer != 0)
      continue;
    /* Skip windows with zero size (overlays, status items) */
    CFDictionaryRef frame = (CFDictionaryRef)CFDictionaryGetValue(window, CFSTR("kCGWindowFrame"));
    if (frame) {
      CFNumberRef w_val = NULL, h_val = NULL;
      CFDictionaryGetValueIfPresent(frame, CFSTR("Width"), (const void **)&w_val);
      CFDictionaryGetValueIfPresent(frame, CFSTR("Height"), (const void **)&h_val);
      double ww = 0, hh = 0;
      if (w_val) CFNumberGetValue(w_val, kCFNumberDoubleType, &ww);
      if (h_val) CFNumberGetValue(h_val, kCFNumberDoubleType, &hh);
      if (ww < 1 || hh < 1)
        continue;
    }
    CFStringRef owner = (CFStringRef)CFDictionaryGetValue(window, kCGWindowOwnerName);
    if (owner == NULL)
      continue;
    char name[1024];
    if (CFStringGetCString(owner, name, sizeof(name), kCFStringEncodingUTF8)) {
      printf("%s\n", name);
      CFRelease(windows);
      return 0;
    }
  }
  CFRelease(windows);
  fprintf(stderr, "cghelper: no frontmost window found\n");
  return 4;
}

int main(int argc, char **argv) {
  signal(SIGTERM, request_stop);
  signal(SIGINT, request_stop);
  if (argc < 2) {
    usage();
    return 2;
  }
  if (requires_accessibility(argv[1]) && !AXIsProcessTrusted()) {
    fprintf(stderr, "cghelper: Accessibility trust missing\n");
    return 5;
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
  if (strcmp(argv[1], "displays") == 0)
    return print_display_layout();
  if (strcmp(argv[1], "frontmost") == 0)
    return print_frontmost_window_owner();
  if (strcmp(argv[1], "focused") == 0)
    return print_focused_metadata();
  if (strcmp(argv[1], "element") == 0 && argc == 4)
    return print_position_metadata(atoi(argv[2]), atoi(argv[3]));
  if (strcmp(argv[1], "trusted") == 0) {
    printf("%d\n", AXIsProcessTrusted() ? 1 : 0);
    return 0;
  }
  if (strcmp(argv[1], "screen-recording") == 0) {
    printf("%d\n", CGPreflightScreenCaptureAccess() ? 1 : 0);
    return 0;
  }
  if (strcmp(argv[1], "move") == 0 && argc == 4) {
    mouse_at(kCGEventMouseMoved, atoi(argv[2]), atoi(argv[3]), 0, 0);
    return 0;
  }
  if (strcmp(argv[1], "movebatch") == 0 && argc == 3) {
    int gap = atoi(argv[2]);
    int x, y;
    int count = 0;
    while (!stop_requested && scanf("%d %d", &x, &y) == 2) {
      // no trailing sleep after the last point
      if (count > 0 && gap > 0)
        usleep((useconds_t)gap);
      if (stop_requested)
        break;
      mouse_at(kCGEventMouseMoved, x, y, 0, 0);
      count++;
    }
    printf("%d\n", count);
    return stop_requested ? 130 : 0;
  }
  if (strcmp(argv[1], "click") == 0 && argc == 6) {
    int x = atoi(argv[2]), y = atoi(argv[3]);
    int btn = atoi(argv[4]), n = atoi(argv[5]);
    int completed = 0;
    CGEventType down = btn == 1 ? kCGEventRightMouseDown : kCGEventLeftMouseDown;
    CGEventType up = btn == 1 ? kCGEventRightMouseUp : kCGEventLeftMouseUp;
    for (int i = 1; i <= (n > 2 ? 2 : (n < 1 ? 1 : n)); i++) {
      if (stop_requested)
        break;
      mouse_at(down, x, y, btn, i);
      mouse_at(up, x, y, btn, 0);
      completed++;
      if (n == 2 && i == 1)
        usleep(80000);
    }
    printf("%d\n", completed);
    return stop_requested ? 130 : 0;
  }
  if (strcmp(argv[1], "drag") == 0 && argc == 6) {
    int x1 = atoi(argv[2]), y1 = atoi(argv[3]);
    int release_x = x1, release_y = y1;
    (void)argv[4];
    (void)argv[5];
    mouse_at(kCGEventLeftMouseDown, x1, y1, 0, 1);
    int x, y;
    int count = 0;
    while (!stop_requested && scanf("%d %d", &x, &y) == 2) {
      mouse_at(kCGEventLeftMouseDragged, x, y, 0, 0);
      release_x = x;
      release_y = y;
      count++;
    }
    mouse_at(kCGEventLeftMouseUp, release_x, release_y, 0, 0);
    printf("%d\n", count);
    return stop_requested ? 130 : 0;
  }
  if (strcmp(argv[1], "scroll") == 0 && argc == 5) {
    int dy = atoi(argv[2]), dx = atoi(argv[3]), count = atoi(argv[4]);
    // Ponytail ultra: loop ticks in C with one spawn and no artificial delay.
    int completed = 0;
    for (int i = 0; i < (count < 1 ? 1 : count) && !stop_requested; i++) {
      CGEventRef e = CGEventCreateScrollWheelEvent(NULL, kCGScrollEventUnitLine, 2, dy, dx);
      if (e == NULL) {
        fprintf(stderr, "cghelper: scroll create failed\n");
        return 3;
      }
      post(e);
      completed++;
    }
    printf("%d\n", completed);
    return stop_requested ? 130 : 0;
  }
  if (strcmp(argv[1], "type") == 0 && argc == 3) {
    return type_stdin(atoi(argv[2]));
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
      CGEventSetFlags(e, (CGEventFlags)flags);
      post(e);
    }
    finish_keyboard_delivery();
    printf("1\n");
    return 0;
  }
  if (strcmp(argv[1], "release") == 0 && argc == 2) {
    CGEventRef location_event = CGEventCreate(NULL);
    if (location_event == NULL)
      return 3;
    CGPoint location = CGEventGetLocation(location_event);
    CFRelease(location_event);
    mouse_at(kCGEventLeftMouseUp, (int)location.x, (int)location.y, 0, 0);
    mouse_at(kCGEventRightMouseUp, (int)location.x, (int)location.y, 1, 0);
    for (int code = 0; code < 128; code++) {
      CGEventRef event = CGEventCreateKeyboardEvent(
          NULL, (CGKeyCode)code, false);
      if (event != NULL)
        post(event);
    }
    return 0;
  }
  usage();
  return 2;
}
