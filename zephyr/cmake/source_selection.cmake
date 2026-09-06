set(NUCODE_ARDUINO_CORE_SOURCES)

if(CONFIG_NUCODE_ARDUINO_RUNTIME)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/main.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/runtime_scheduler.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_API)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_API_ROOT}/api/Common.cpp"
    "${NUCODE_ARDUINO_API_ROOT}/api/Print.cpp"
    "${NUCODE_ARDUINO_API_ROOT}/api/Stream.cpp"
    "${NUCODE_ARDUINO_API_ROOT}/api/String.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/api_compat.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/diagnostics.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/peripheral_inventory.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/peripheral_stubs.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_random.cpp"
  )

  if(CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE LESS 1)
    message(FATAL_ERROR
      "Arduino String requires a bounded positive CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE"
    )
  endif()
endif()

if(CONFIG_NUCODE_ARDUINO_IO_OWNERSHIP)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/io_resource_manager.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/resource/IoResourceTable.cpp"
    "${NUCODE_ARDUINO_VARIANT_ROOT}/io_resource_registry.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_GPIO)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_digital.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_pulse_shift.cpp"
    "${NUCODE_ARDUINO_VARIANT_ROOT}/variant.cpp"
  )

  if(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
    list(APPEND NUCODE_ARDUINO_CORE_SOURCES
      "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_interrupt.cpp"
    )
  endif()
endif()

if(CONFIG_NUCODE_ARDUINO_TIME)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_time.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/time_backend_nrf54.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL)
  if(NOT CONFIG_SERIAL_SUPPORT_INTERRUPT)
    message(FATAL_ERROR
      "Arduino Serial RX requires CONFIG_SERIAL_SUPPORT_INTERRUPT from the selected UART driver"
    )
  endif()

  foreach(conflict_symbol IN ITEMS
    SHELL_BACKEND_SERIAL
    CONSOLE_HANDLER
    CONSOLE_GETCHAR
    UART_MCUMGR
    MCUMGR_TRANSPORT_UART
    MCUMGR_TRANSPORT_UART_ASYNC
    LOG_BACKEND_UART_ASYNC
    TRACING_BACKEND_UART
  )
    if(CONFIG_${conflict_symbol})
      message(FATAL_ERROR
        "Arduino Serial RX cannot share the chosen UART callback with CONFIG_${conflict_symbol}"
      )
    endif()
  endforeach()

  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/HardwareSerial.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/SerialFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/serial/SerialFabricRegistry.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/serial/SerialFabricLifecycle.cpp"
    "${NUCODE_ARDUINO_VARIANT_ROOT}/serial_fabric_routes.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/UarteFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/SpimFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/SpisFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIM)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/TwimFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIS)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/TwisFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_ANALOG_FABRIC)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/AnalogFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/analog/SaadcFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/analog/PwmSequenceFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_EVENT_FABRIC)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/EventFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/event/EventFabricRegistry.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/event/TimerFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/event/EguFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/event/GpioteFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/event/DppiFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/event/PpibFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_STREAM_FABRIC)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/StreamFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/stream/PdmFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/stream/I2sFabric.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/stream/QdecFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SYSTEM_FABRIC)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/SystemFabric.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SERIAL1 OR
   CONFIG_NUCODE_ARDUINO_WIRE OR
   CONFIG_NUCODE_ARDUINO_SPI OR
   CONFIG_NUCODE_ARDUINO_PWM)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/RuntimePeripheralRoute.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/RuntimePeripheralRouteRecovery.cpp"
    "${NUCODE_ARDUINO_VARIANT_ROOT}/peripheral_routes.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_WIRE)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/Wire.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_SPI)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/SPI.cpp"
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/spi/SpiZephyrBackend.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_ADC OR CONFIG_NUCODE_ARDUINO_PWM)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_analog.cpp"
  )
endif()

if(CONFIG_NUCODE_ARDUINO_PWM)
  list(APPEND NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/PwmRuntime.cpp"
    "${NUCODE_ARDUINO_VARIANT_ROOT}/pwm_runtime_routes.cpp"
  )
endif()
