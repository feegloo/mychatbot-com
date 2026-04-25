import { mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import App from './App.vue'

describe('App shell', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: vi.fn().mockResolvedValue({ message: 'Hello World' }),
      }),
    )
  })

  it('renders left and right columns with HomeHero', () => {
    const wrapper = mount(App)

    expect(wrapper.find('[data-testid="menu-column"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="content-column"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Upload securely')
    expect(wrapper.find('img.home-logo').exists()).toBe(true)
  })
})
