module.exports = {
  okapi: { 'url':'reshare-2-okapi.folio-dev-us-east-1-1.folio-dev.indexdata.com', 'tenant':'reshare_2' },
  config: {
    showHomeLink: true,
    welcomeMessage: 'ui-rs.front.welcome',
    platformName: 'ReShare',
    platformDescription: 'ReShare platform',
    hasAllPerms: false,
    showDevInfo: true,
    staleBundleWarning: { path: '/index.html', header: 'last-modified', interval: 5 },
  },
  modules: {
    '@folio/users': {},
    '@folio/developer': {},
    "@folio/tenant-settings": {},
  },
  branding: {
    style: {},
    logo: {
      src: './tenant-assets/reshare-logo.png',
      alt: 'ReShare 2',
    },
    favicon: {
      src: './tenant-assets/reshare-favicon.jpg',
    },
  },
};
