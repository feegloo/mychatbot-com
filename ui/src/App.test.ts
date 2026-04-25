import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App shell', () => {
  it('renders left and right columns with HomeHero', () => {
    const wrapper = mount(App)

    expect(wrapper.find('[data-testid="menu-column"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="content-column"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Upload securely')
    expect(wrapper.find('img.home-logo').exists()).toBe(true)
  })
})
