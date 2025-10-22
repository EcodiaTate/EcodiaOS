// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config, { isServer }) => {
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/,
      use: 'raw-loader',
    })
    return config
  },
}
// next.config.js
const withTM = require('next-transpile-modules')(['three'])
module.exports = withTM({
  webpack(config) {
    config.module.rules.push({
      test: /\.(glsl|vs|fs)$/,
      use: ['babel-loader', 'glslify-loader'],
    })
    return config
  },
})

module.exports = nextConfig
