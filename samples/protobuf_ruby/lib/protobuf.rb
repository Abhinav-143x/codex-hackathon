# lib/protobuf.rb — Minimal protobuf Ruby enum helper (sample for PR #27848 fix)
# This is a self-contained reproduction of the enum_getter fix.

module Google
  module Protobuf
    module EnumHelper
      # Returns the enum value for the given key, or nil if not found.
      def enum_getter(enum_module, key)
        return nil if enum_module.nil? || !enum_module.respond_to?(:constants)
        matching = enum_module.constants.select { |c|
          enum_module.const_get(c) == key
        }
        return nil if matching.empty?
        matching.first
      end
    end
  end
end
