/**
 * Project_Alice Service Worker for PWA Web Push & Notification Actions
 */
const CACHE_NAME = 'alice-admin-v2';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => clients.claim())
  );
});

// ==========================================
// Web Push Notification Handler
// ==========================================
self.addEventListener('push', (event) => {
  let data = {
    title: 'Project ALICE 通知',
    body: '新しいシステム通知があります',
    icon: '/static/admin/alice_logo.jpg',
    badge: '/static/admin/alice_logo.jpg',
    tag: 'alice-general-notification',
    data: { url: '/admin' }
  };

  if (event.data) {
    try {
      const json = event.data.json();
      data = { ...data, ...json };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/static/admin/alice_logo.jpg',
    badge: data.badge || '/static/admin/alice_logo.jpg',
    tag: data.tag || 'alice-alert',
    renotify: true,
    vibrate: [200, 100, 200, 100, 200],
    data: data.data || { url: '/admin' },
    actions: [
      { action: 'open', title: '確認・承認' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// ==========================================
// Notification Click Handler
// ==========================================
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/admin';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus existing window if open
      for (const client of clientList) {
        if (client.url.includes('/admin') && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Open new window if none active
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
