import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App shell', () => {
  it('renders left and right columns', () => {
    const wrapper = mount(App)

    expect(wrapper.find('[data-testid="menu-column"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="content-column"]').exists()).toBe(true)
  })
})
