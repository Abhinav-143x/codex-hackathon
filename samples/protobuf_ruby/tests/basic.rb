# tests/basic.rb — Tests for the enum_getter fix (PR #27848)
require 'minitest/autorun'
require_relative '../lib/protobuf'

module TestEnums
  UNKNOWN = 0
  FOO     = 1
  BAR     = 2
end

class TestEnumGetter < Minitest::Test
  include Google::Protobuf::EnumHelper

  def test_enum_getter
    # Key present → should return the constant name
    result = enum_getter(TestEnums, 1)
    assert_equal :FOO, result, "Expected :FOO for value 1"
  end

  def test_enum_getter_missing_key
    # Key absent → should return nil (not raise)
    result = enum_getter(TestEnums, 999)
    assert_nil result, "Expected nil for missing key 999"
  end

  def test_enum_getter_nil_module
    # Nil module → should return nil (not raise NoMethodError)
    result = enum_getter(nil, 1)
    assert_nil result, "Expected nil when enum_module is nil"
  end

  def test_enum_getter_zero_value
    result = enum_getter(TestEnums, 0)
    assert_equal :UNKNOWN, result
  end
end
