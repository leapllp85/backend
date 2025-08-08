from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, EmployeeDesignation

class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'first_name', 'last_name')
        extra_kwargs = {
            'password': {'write_only': True},
            'id': {'read_only': True}
        }

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name']
        )
        return user

class ProfileSerializer(serializers.ModelSerializer):

    phone_number = serializers.CharField(required=False)
    employee_designation = serializers.SlugRelatedField(
        slug_field='name',
        queryset=EmployeeDesignation.objects.all(),
        required=False
    )
    fullname = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Profile
        fields = ('phone_number', 'date_of_birth', 'employee_designation', 'supervisor', 'is_verified', 'fullname')

        extra_kwargs = {
            'phone_number': {'required': False},
            'date_of_birth': {'required': False},
            'employee_designation': {'required': False},
            'supervisor': {'required': False},
            'is_verified': {'required': False},
        }

    def get_fullname(self, obj):
        return obj.user.get_full_name()

    def create(self, validated_data):
        profile, _ = Profile.objects.get_or_create(user=self.context['request'].user)
        profile.phone_number = validated_data.get('phone_number', profile.phone_number)
        profile.date_of_birth = validated_data.get('date_of_birth', profile.date_of_birth)
        profile.employee_designation = validated_data.get('employee_designation', profile.employee_designation)
        profile.supervisor = validated_data.get('supervisor', profile.supervisor)
        profile.save()
        return profile

class EmployeeDesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeDesignation
        fields = ('name',)
